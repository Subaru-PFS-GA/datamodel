import os
import sys
import unittest

import numpy as np
import astropy.units as u

import lsst.utils.tests
import lsst.geom

from pfs.datamodel.pfsConfig import PfsConfig, TargetType, FiberStatus, PfsDesign, GuideStars

display = None


class PfsConfigTestCase(lsst.utils.tests.TestCase):
    def setUp(self):
        self.numFibers = 2396

        # TargetType
        self.numSky = 240
        self.numFluxStd = 300
        self.numUnassigned = 10
        self.numEngineering = 10
        self.numSuNSS_Imaging = 5
        self.numSuNSS_Diffuse = 3
        self.numObject = self.numFibers - (self.numSky + self.numFluxStd +
                                           self.numUnassigned + self.numEngineering +
                                           self.numSuNSS_Imaging + self.numSuNSS_Diffuse)

        # FiberStatus
        self.numBroken = 3
        self.numBlocked = 2
        self.numBlackSpot = 1
        self.numUnilluminated = 3
        self.numGood = self.numFibers - (self.numBroken + self.numBlocked +
                                         self.numBlackSpot + self.numUnilluminated)

        self.raBoresight = 60.0  # degrees
        self.decBoresight = 30.0  # degrees
        self.posAng = 0.0  # degrees
        self.arms = 'brn'
        self.fov = 1.5*lsst.geom.degrees
        self.pfiScale = 800000.0/self.fov.asDegrees()  # microns/degree
        self.pfiErrors = 10  # microns

        self.pfsDesignId = 12345
        self.visit0 = 67890
        self.fiberId = np.array(list(reversed(range(self.numFibers))))
        rng = np.random.RandomState(12345)
        self.tract = rng.uniform(high=30000, size=self.numFibers).astype(int)
        self.patch = ["%d,%d" % tuple(xy.tolist()) for
                      xy in rng.uniform(high=15, size=(self.numFibers, 2)).astype(int)]

        boresight = lsst.geom.SpherePoint(self.raBoresight*lsst.geom.degrees,
                                          self.decBoresight*lsst.geom.degrees)
        radius = np.sqrt(rng.uniform(size=self.numFibers))*0.5*self.fov.asDegrees()  # degrees
        theta = rng.uniform(size=self.numFibers)*2*np.pi  # radians
        coords = [boresight.offset(tt*lsst.geom.radians, rr*lsst.geom.degrees) for
                  rr, tt in zip(radius, theta)]
        self.ra = np.array([cc.getRa().asDegrees() for cc in coords])
        self.dec = np.array([cc.getDec().asDegrees() for cc in coords])
        self.pfiNominal = (self.pfiScale*np.array([(rr*np.cos(tt), rr*np.sin(tt)) for
                                                   rr, tt in zip(radius, theta)])).astype(np.float32)
        self.pfiCenter = (self.pfiNominal +
                          rng.normal(scale=self.pfiErrors, size=(self.numFibers, 2))).astype(np.float32)

        self.catId = rng.uniform(high=23, size=self.numFibers).astype(int)
        self.objId = rng.uniform(high=2**63, size=self.numFibers).astype(int)

        self.targetType = np.array([int(TargetType.SKY)]*self.numSky +
                                   [int(TargetType.FLUXSTD)]*self.numFluxStd +
                                   [int(TargetType.SCIENCE)]*self.numObject +
                                   [int(TargetType.UNASSIGNED)]*self.numUnassigned +
                                   [int(TargetType.ENGINEERING)]*self.numEngineering +
                                   [int(TargetType.SUNSS_DIFFUSE)]*self.numSuNSS_Diffuse +
                                   [int(TargetType.SUNSS_IMAGING)]*self.numSuNSS_Imaging)
        rng.shuffle(self.targetType)
        self.fiberStatus = np.array([int(FiberStatus.BROKENFIBER)]*self.numBroken +
                                    [int(FiberStatus.BLOCKED)]*self.numBlocked +
                                    [int(FiberStatus.BLACKSPOT)]*self.numBlackSpot +
                                    [int(FiberStatus.UNILLUMINATED)]*self.numUnilluminated +
                                    [int(FiberStatus.GOOD)]*self.numGood)
        rng.shuffle(self.fiberStatus)

        fiberMagnitude = [22.0, 23.5, 25.0, 26.0]
        fiberFluxes = [(f * u.ABmag).to_value(u.nJy) for f in fiberMagnitude]

        self.fiberFlux = [np.array(fiberFluxes if
                                   tt in (TargetType.SCIENCE, TargetType.FLUXSTD) else [])
                          for tt in self.targetType]

        # For these tests, assign psfFlux and totalFlux
        # the same value as the fiber flux
        self.psfFlux = [fFlux for fFlux in self.fiberFlux]
        self.totalFlux = [fFlux for fFlux in self.fiberFlux]

        # Assign corresponding errors as 1% of fiberFlux
        fluxError = [0.01 * f for f in fiberFluxes]
        self.fiberFluxErr = [np.array(fluxError if
                                      tt in (TargetType.SCIENCE, TargetType.FLUXSTD) else [])
                             for tt in self.targetType]
        self.psfFluxErr = [e for e in self.fiberFluxErr]
        self.totalFluxErr = [e for e in self.fiberFluxErr]

        self.filterNames = [["g", "i", "y", "H"] if tt in (TargetType.SCIENCE, TargetType.FLUXSTD) else []
                            for tt in self.targetType]

        self.guideStars = GuideStars.empty()

    def _makeInstance(self, Class, **kwargs):
        """Construct a PfsDesign or PfsConfig using default values

        Parameters
        ----------
        Class : `type`
            Class of instance to construct (``PfsConfig`` or ``PfsDesign).
        **kwargs : `dict`
            Arguments for the constructor. Any missing arguments
            will be provided with defaults from the test.

        Returns
        -------
        instance : ``Class``
            Constructed PfsConfig or PfsDesign.
        """
        # fiberStatus is special, for backwards-compatibility reasons
        needNames = set(Class._keywords + Class._scalars + ["fiberStatus"])
        haveNames = set(kwargs.keys())
        assert len(haveNames - needNames) == 0, "Unrecognised argument"
        for name in needNames - haveNames:
            kwargs[name] = getattr(self, name)
        return Class(**kwargs)

    def makePfsDesign(self, **kwargs):
        """Construct a PfsDesign using default values from the test

        Parameters
        ----------
        **kwargs : `dict`
            Arguments for the `PfsDesign` constructor. Any missing arguments
            will be provided with defaults from the test.

        Returns
        -------
        pfsDesign : `PfsDesign`
            Constructed pfsConfig.
        """
        return self._makeInstance(PfsDesign, **kwargs)

    def makePfsConfig(self, **kwargs):
        """Construct a PfsConfig using default values from the test

        Parameters
        ----------
        **kwargs : `dict`
            Arguments for the `PfsConfig` constructor. Any missing arguments
            will be provided with defaults from the test.

        Returns
        -------
        pfsConfig : `PfsConfig`
            Constructed pfsConfig.
        """
        return self._makeInstance(PfsConfig, **kwargs)

    def assertPfsConfig(self, lhs, rhs):
        for value in ("pfsDesignId", "visit0"):
            self.assertEqual(getattr(lhs, value), getattr(rhs, value), value)
        for value in ("raBoresight", "decBoresight", "posAng", "arms"):
            # Our FITS header writer can introduce some tiny roundoff error
            self.assertAlmostEqual(getattr(lhs, value), getattr(rhs, value), 14, value)
        for value in ("fiberId", "tract", "ra", "dec", "catId", "objId",
                      "pfiCenter", "pfiNominal", "targetType", "fiberStatus"):
            np.testing.assert_array_equal(getattr(lhs, value), getattr(rhs, value), value)
        self.assertEqual(len(lhs.patch), len(rhs.patch))
        self.assertEqual(len(lhs.fiberFlux), len(rhs.fiberFlux))
        self.assertEqual(len(lhs.filterNames), len(rhs.filterNames))
        for ii in range(len(lhs)):
            self.assertEqual(lhs.patch[ii], rhs.patch[ii], "patch[%d]" % (ii,))
            np.testing.assert_array_almost_equal(lhs.fiberFlux[ii], rhs.fiberFlux[ii],
                                                 decimal=4,
                                                 err_msg="fiberFlux[%d]" % (ii,))
            self.assertListEqual(lhs.filterNames[ii], rhs.filterNames[ii], "filterNames[%d]" % (ii,))

    def testBasic(self):
        """Test basic operation of PfsConfig"""
        config = self.makePfsConfig()

        dirName = os.path.splitext(__file__)[0]
        if not os.path.exists(dirName):
            os.makedirs(dirName)

        filename = os.path.join(dirName, config.filename)
        if os.path.exists(filename):
            os.unlink(filename)

        try:
            config.write(dirName=dirName)
            other = PfsConfig.read(self.pfsDesignId, self.visit0, dirName=dirName)
            self.assertPfsConfig(config, other)
        except Exception:
            raise  # Leave file for manual inspection
        else:
            os.unlink(filename)

    def testBadCtor(self):
        """Test bad constructor calls"""
        def extendArray(array):
            """Double the length of the array"""
            return np.concatenate((array, array))

        def extendList(values):
            """Double the length of the list"""
            return values + values

        # Longer arrays
        for name in ("fiberId", "tract", "patch", "ra", "dec", "catId", "objId"):
            with self.assertRaises(RuntimeError):
                self.makePfsConfig(**{name: extendArray(getattr(self, name))})

        # Arrays with bad enums
        targetType = self.targetType.copy()
        targetType[self.numFibers//2] = -1
        with self.assertRaises(ValueError):
            self.makePfsConfig(targetType=targetType)
        fiberStatus = self.fiberStatus.copy()
        fiberStatus[self.numFibers//2] = -1
        with self.assertRaises(ValueError):
            self.makePfsConfig(fiberStatus=fiberStatus)

        # Fluxes
        for name in ("fiberFlux", "psfFlux", "totalFlux", "fiberFluxErr", "psfFluxErr", "totalFluxErr"):
            array = [extendArray(mag) if ii == self.numFibers//2 else mag
                     for ii, mag in enumerate(getattr(self, name))]
            with self.assertRaises(RuntimeError):
                self.makePfsConfig(**{name: array})

        # Arrays of points
        for name in ("pfiCenter", "pfiNominal"):
            array = getattr(self, name)
            array = np.concatenate((array, array), axis=1)
            with self.assertRaises(RuntimeError):
                self.makePfsConfig(**{name: array})

    def testFromPfsDesign(self):
        """Test PfsConfig.fromPfsDesign"""
        design = self.makePfsDesign()
        config = self.makePfsConfig()
        self.assertPfsConfig(PfsConfig.fromPfsDesign(design, self.visit0, self.pfiCenter), config)

    def testFromEmptyGuideStars(self):
        """Check that an empty GuideStars instance is correctly instantiated
        if a None value is passed to the corresponding constructor argument
        """
        design = self.makePfsDesign(guideStars=None)
        self.checkGsEmpty(design)

        config = self.makePfsConfig(guideStars=None)
        self.checkGsEmpty(config)

        # Check that a non-empty GuideStar instance can be passed during construction.
        gsNotEmpty = GuideStars.empty()  # Using a tweaked version of an empty GuideStars instance.
        telElev = 123
        gsNotEmpty.telElev = telElev

        design = self.makePfsDesign(guideStars=gsNotEmpty)
        gs = design.guideStars
        self.checkGsArrayAttributesEmpty(gs)
        self.assertEqual(gs.telElev, telElev)

    def checkGsEmpty(self, design):
        """Check that the contents of the
        GuideStars attribute of the PfsDesign is empty.
        """
        gs = design.guideStars
        self.checkGsArrayAttributesEmpty(gs)
        self.assertEqual(gs.telElev, 0.0)
        self.assertEqual(gs.guideStarCatId, 0)

    def checkGsArrayAttributesEmpty(self, gs):
        """Check that the array-like
        attributes of the passed GuideStars
        instance are empty.
        """
        for att in ['objId', 'epoch',
                    'ra', 'dec',
                    'pmRa', 'pmDec',
                    'parallax', 'magnitude',
                    'passband', 'color',
                    'agId', 'agX', 'agY',
                    'epoch']:
            value = getattr(gs, att)
            self.assertTrue(value is not None)
            self.assertTrue(len(value) == 0)

    def testGetitem(self):
        """Test __getitem__"""
        select = np.array([ii % 2 == 0 for ii in range(self.numFibers)], dtype=bool)
        numSelected = select.sum()
        assert numSelected < self.numFibers
        pfsConfig = self.makePfsConfig()
        sub = pfsConfig[select]
        self.assertEqual(len(sub), numSelected)
        self.assertFloatsEqual(sub.fiberId, pfsConfig.fiberId[select])
        self.assertFloatsEqual(sub.objId, pfsConfig.objId[select])

    def testSelect(self):
        """Test select method"""
        pfsConfig = self.makePfsConfig()

        fiberId = self.fiberId[3]
        sub = pfsConfig.select(fiberId=fiberId)
        self.assertEqual(len(sub), 1)
        self.assertFloatsEqual(sub.fiberId, fiberId)

        targetType = TargetType.FLUXSTD
        sub = pfsConfig.select(targetType=targetType)
        self.assertEqual(len(sub), self.numFluxStd)
        self.assertFloatsEqual(sub.targetType, targetType)

        fiberStatus = FiberStatus.BROKENFIBER
        sub = pfsConfig.select(fiberStatus=fiberStatus)
        self.assertEqual(len(sub), self.numBroken)
        self.assertFloatsEqual(sub.fiberStatus, fiberStatus)

        index = 2*self.numFibers//3
        sub = pfsConfig.select(catId=pfsConfig.catId[index], tract=pfsConfig.tract[index],
                               patch=pfsConfig.patch[index], objId=pfsConfig.objId[index])
        self.assertEqual(len(sub), 1)
        self.assertEqual(sub.catId[0], pfsConfig.catId[index])
        self.assertEqual(sub.tract[0], pfsConfig.tract[index])
        self.assertEqual(sub.patch[0], pfsConfig.patch[index])
        self.assertEqual(sub.objId[0], pfsConfig.objId[index])

        indices = np.array([42, 37, 1234])
        sub = pfsConfig.select(fiberId=self.fiberId[indices])
        self.assertEqual(len(sub), len(indices))
        self.assertFloatsEqual(sub.fiberId, pfsConfig.fiberId[np.sort(indices)])

        fiberStatus = (FiberStatus.BROKENFIBER, FiberStatus.BLOCKED)
        sub = pfsConfig.select(fiberStatus=fiberStatus)
        self.assertEqual(len(sub), self.numBroken + self.numBlocked)
        select = np.zeros(len(pfsConfig), dtype=bool)
        for ff in fiberStatus:
            select |= pfsConfig.fiberStatus == ff
        self.assertFloatsEqual(sub.fiberStatus, pfsConfig[select].fiberStatus)

    def testSelectFiber(self):
        """Test selectFiber"""
        pfsConfig = self.makePfsConfig()

        index = 37
        result = pfsConfig.selectFiber(pfsConfig.fiberId[index])
        self.assertEqual(result, 37)

        index = np.array([42, 37, 1234])
        result = pfsConfig.selectFiber(pfsConfig.fiberId[index])
        self.assertFloatsEqual(result, sorted(index))  # Note the need to sort


class TestMemory(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    setup_module(sys.modules["__main__"])
    from argparse import ArgumentParser
    parser = ArgumentParser(__file__)
    parser.add_argument("--display", help="Display backend")
    args, argv = parser.parse_known_args()
    display = args.display
    unittest.main(failfast=True, argv=[__file__] + argv)
