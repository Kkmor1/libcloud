#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app/libcloud')

import unittest
from libcloud.test.common.test_aws_signature_v4 import AWSSignatureV4OfficialTestCases, AWSSignatureV4IntegrationWithRequestsMock

loader = unittest.TestLoader()
suite = unittest.TestSuite()
suite.addTests(loader.loadTestsFromTestCase(AWSSignatureV4OfficialTestCases))
suite.addTests(loader.loadTestsFromTestCase(AWSSignatureV4IntegrationWithRequestsMock))

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
