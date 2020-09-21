import os
import re
from types import SimpleNamespace

import numpy as np

from .utils import astropyHeaderToDict, astropyHeaderFromDict

__all__ = ("CalibIdentity", "PfsFiberProfiles")


class CalibIdentity(SimpleNamespace):
    """Keyword-value pairs describing a calibration

    Parameters
    ----------
    obsDate : `str`
        Observation date of calibration, in ISO-8601 format.
    spectrograph : `int`
        Spectrograph number.
    arm : `str`
        Arm letter: ``b``, ``r``, ``n``, ``m``.
    visit0 : `int`
        First visit number calibration was constructed from.
    """

    elements = ("obsDate", "spectrograph", "arm", "visit0")
    """Required keywords"""

    def __init__(self, obsDate, spectrograph, arm, visit0):
        super().__init__(obsDate=obsDate, spectrograph=int(spectrograph), arm=arm, visit0=int(visit0))

    @classmethod
    def fromDict(cls, identity):
        """Build from a `dict`

        Parameters
        ----------
        identity : `dict`
            The data identifier.

        Returns
        -------
        self : `CalibIdentity`
            Calibration identity.s
        """
        kwargs = {elem: identity[elem] for elem in cls.elements}
        return cls(**kwargs)

    def toDict(self):
        """Convert to a `dict`

        Returns
        -------
        calibId : `dict`
            Data identity for calibration.
        """
        return {elem: getattr(self, elem) for elem in self.elements}


class PfsFiberProfiles:
    """The shape of the fiber trace as a function of detector row

    The shape for each fiber is expressed empirically by oversampled vectors at
    various positions up the trace. The profile for a fiber for a particular row
    can be obtained by iterpolating between these.

    Parameters
    ----------
    identity : `pfs.datamodel.CalibIdentity`
        Identity of calib data.
    fiberId : array_like of `int`, length ``N``
        Fiber identifiers.
    radius : array_like of `int`, length ``N``
        Half-size of the oversampled vectors for each fiber, for the regular
        image sampling.
    oversample : array_like of `float`, length ``N``
        Oversampling factor for each fiber.
    rows : iterable (length ``N``) of array_like of `float` (length ``M``)
        Arrays for each fiber indicating the detector row at which the
        corresponding profile is measured. ``M`` is the number of profiles for
        that fiber.
    profiles : iterable (length ``N``) of array_like of `float` (shape ``(M,P)``)
        Empirical profiles for each fiber. ``M`` is the number of profiles for
        that fiber. ``P = int(2*(radius + 1)*oversample) + 1``. The
        profile arrays may be of type `numpy.ma.masked_array`, in order to
        indicate profile values that should be ignored.
    norm : iterable (length ``N``) of array_like of `float` (length ``Q``)
        Normalisation to apply when extracting spectrum from the image. ``Q``
        is the height of the detector; or it may be ``0`` if no normalisation
        is to be applied.
    metadata : `dict` mapping `str` to POD
        Keyword-value pairs for the header.
    """

    filenameFormat = "pfsFiberProfiles-%(obsDate)10s-%(visit0)06d-%(arm)1s%(spectrograph)1d.fits"
    """Format for filename (`str`)

    Should include formatting directives for the ``identity`` dict.
    """

    filenameRegex = (r"pfsFiberProfiles-(?P<obsDate>\S{10})-(?P<visit0>\d{6})-"
                     r"(?P<arm>\S)(?P<spectrograph>\d).fits")
    """Regex for extracting dataId from filename (`str`)

    Should capture the regex capture directives for the ``identity`` dict.
    """

    def __init__(self, identity, fiberId, radius, oversample, rows, profiles, norm, metadata):
        self.identity = identity
        self.fiberId = np.array(fiberId)
        self.radius = np.array(radius)
        self.oversample = np.array(oversample)
        self.rows = [np.array(rr) for rr in rows]
        self.profiles = [np.ma.masked_array(pp) for pp in profiles]
        self.norm = [np.array(nn) for nn in norm]
        self.metadata = metadata

        self.length = len(fiberId)
        self.validate()

    def validate(self):
        """Validate that all the arrays are of the expected shape"""
        assert self.fiberId.shape == (self.length,)
        assert self.radius.shape == (self.length,)
        assert self.oversample.shape == (self.length,)
        assert len(self.rows) == self.length
        assert len(self.profiles) == self.length
        assert all(len(rr) == len(pp) for rr, pp in zip(self.rows, self.profiles))
        for prof, rad, samp in zip(self.profiles, self.radius, self.oversample):
            assert all(len(pp) == int(2*(rad + 1)*samp) + 1 for pp in prof)
        assert len(self.norm) == self.length

    def __len__(self):
        """Return number of profiles"""
        return self.length

    def __str__(self):
        """Stringify"""
        return "%s{%d profiles}" % (self.__class__.__name__, self.length)

    @property
    def filename(self):
        """Filename, without directory"""
        return self.getFilename(self.identity)

    @classmethod
    def getFilename(cls, identity):
        """Calculate filename

        Parameters
        ----------
        identity : `pfs.datamodel.CalibIdentity`
            Identity of the data.

        Returns
        -------
        filename : `str`
            Filename, without directory.
        """
        return cls.filenameFormat % identity.getDict()

    @classmethod
    def parseFilename(cls, path):
        """Parse filename to get the file's identity

        Uses the class attributes ``filenameRegex`` and ``filenameKeys`` to
        construct the identity from the filename.

        Parameters
        ----------
        path : `str`
            Path to the file of interest.

        Returns
        -------
        identity : `pfs.datamodel.Identity`
            Identity of the data of interest.
        """
        dirName, fileName = os.path.split(path)
        matches = re.search(cls.filenameRegex, fileName)
        if not matches:
            raise RuntimeError("Unable to parse filename: %s" % (fileName,))
        return CalibIdentity.fromDict(matches.groupdict())

    @classmethod
    def _readImpl(cls, fits, identity):
        """Implementation of reading from a FITS file in memory

        Parameters
        ----------
        fits : `astropy.io.fits.HDUList`
            FITS file in memory.
        identity : `pfs.datamodel.CalibIdentity`
            Identity of the calib data.

        Returns
        -------
        self : `PfsFiberProfiles`
            Fiber profiles read from the FITS file.
        """
        metadata = astropyHeaderToDict(fits[0].header)

        hdu = fits["FIBERS"]
        fiberId1 = hdu.data["fiberId"]
        radius = hdu.data["radius"]
        oversample = hdu.data["oversample"]
        norm = hdu.data["norm"]

        hdu = fits["PROFILES"]
        fiberId2 = hdu.data["fiberId"]
        rows = hdu.data["rows"]
        profiles = hdu.data["profiles"]
        masks = hdu.data["masks"]

        numFibers = len(fiberId1)
        fiberRows = []
        fiberProfiles = []
        for ii in range(numFibers):
            select = fiberId2 == fiberId1[ii]
            fiberRows.append(rows[select])
            fiberProfiles.append(np.ma.masked_array(np.array(profiles[select].tolist()),
                                                    mask=(np.array(masks[select].tolist(), dtype=bool) if
                                                          masks[select].size > 0 else False)))

        return cls(identity, fiberId1, radius, oversample, fiberRows, fiberProfiles, norm, metadata)

    @classmethod
    def readFits(cls, filename):
        """Read from FITS file

        This API is intended for use by the LSST data butler, which handles
        translating the desired identity into a filename.

        Parameters
        ----------
        filename : `str`
            Filename of FITS file.

        Returns
        -------
        self : ``cls``
            Constructed instance, from FITS file.
        """
        identity = cls.parseFilename(filename)
        import astropy.io.fits
        with astropy.io.fits.open(filename) as fits:
            return cls._readImpl(fits, identity)

    @classmethod
    def read(cls, identity, dirName="."):
        """Read file given an identity

        This API is intended for use by science users, as it allows selection
        of the correct file by identity (e.g., visit, arm, spectrograph),
        without knowing the file naming convention.

        Parameters
        ----------
        identity : `pfs.datamodel.CalibIdentity`
            Identification of the calib data of interest.
        dirName : `str`, optional
            Directory from which to read.

        Returns
        -------
        self : `PfsFiberArraySet`
            Spectra read from file.
        """
        import astropy.io.fits
        filename = os.path.join(dirName, cls.getFilename(identity))
        with astropy.io.fits.open(filename) as fits:
            return cls._readImpl(fits, identity)

    def writeFits(self, filename):
        """Write to FITS file

        This API is intended for use by the LSST data butler, which handles
        translating the desired identity into a filename.

        Parameters
        ----------
        filename : `str`
            Filename of FITS file.
        """
        fits = self._writeImpl()
        fits.writeto(filename, overwrite=True)

    def write(self, dirName="."):
        """Write to file

        This API is intended for use by science users, as it allows setting the
        correct filename from parameters that make sense, such as which
        exposure, spectrograph, etc.

        Parameters
        ----------
        dirName : `str`, optional
            Directory to which to write.
        """
        filename = os.path.join(dirName, self.filename)
        self.writeFits(filename)

    def _writeImpl(self):
        """Implementation of writing to FITS file

        Returns
        -------
        fits : `astropy.io.fits.HDUList`
            FITS file representation.
        """
        import astropy.io.fits
        header = astropyHeaderFromDict(self.metadata)
        header["OBSTYPE"] = "fiberProfiles"

        fibersHdu = astropy.io.fits.BinTableHDU.from_columns([
            astropy.io.fits.Column("fiberId", format="J", array=self.fiberId),
            astropy.io.fits.Column("radius", format="J", array=self.radius),
            astropy.io.fits.Column("oversample", format="E", array=self.oversample),
            astropy.io.fits.Column("norm", format="PE()", array=self.norm),
        ], name="FIBERS")
        fibersHdu.header["INHERIT"] = True

        # Concatenate the 'rows' and 'profiles' (and split 'profiles' into data+mask)
        numProfiles = sum(len(rr) for rr in self.rows)
        fiberId = np.zeros(numProfiles, dtype=int)
        rows = np.zeros(numProfiles, dtype=float)
        profiles = []
        masks = []
        start = 0
        for ii in range(self.length):
            num = len(self.rows[ii])
            prof = self.profiles[ii]
            fiberId[start:start + num] = self.fiberId[ii]
            rows[start:start + num] = self.rows[ii]
            for pp in prof:
                if isinstance(pp, np.ma.MaskedArray):
                    profiles.append(pp.data)
                    masks.append(pp.mask)
                else:
                    profiles.append(pp)
                    masks.append([])
            start += num

        profilesHdu = astropy.io.fits.BinTableHDU.from_columns([
            astropy.io.fits.Column("fiberId", format="J", array=fiberId),
            astropy.io.fits.Column("rows", format="E", array=rows),
            astropy.io.fits.Column("profiles", format="PE()", array=profiles),
            astropy.io.fits.Column("masks", format="PL()", array=masks),
        ], name="PROFILES")
        profilesHdu.header["INHERIT"] = True

        return astropy.io.fits.HDUList([astropy.io.fits.PrimaryHDU(header=header), fibersHdu, profilesHdu])
