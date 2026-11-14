from pathlib import Path
import re
import unittest

ROOT = Path(__file__).parent

class SupplierSafetyTests(unittest.TestCase):
    def setUp(self):
        self.sql = (ROOT / 'create_supplier.sql').read_text(encoding='utf-8')
        self.ps = (ROOT / 'Invoke-Supplier.ps1').read_text(encoding='utf-8')

    def test_only_test_writes(self):
        self.assertEqual(re.findall(r'INSERT INTO\s+(\w+)\.', self.sql), ['TEST'])
        self.assertNotRegex(self.sql, r'(?i)(?:UPDATE|DELETE|MERGE|ALTER|DROP)\s+(?:\[?OB\]?\.)')

    def test_preview_before_insert(self):
        self.assertLess(self.sql.index('IF @Execute = 0'), self.sql.index('INSERT INTO TEST.'))
        self.assertIn('VALIDATED_NO_INSERT', self.sql)

    def test_error_propagation_and_lock(self):
        self.assertIn("'ROLLBACK' AS ETAT_TRANSACTION;\n    THROW;", self.sql)
        self.assertIn('sp_getapplock', self.sql)
        self.assertIn('TABLOCKX, HOLDLOCK', self.sql)

    def test_confirmation_and_parameters(self):
        self.assertIn("$answer -cne 'CREER TEST'", self.ps)
        self.assertLess(self.ps.index("$answer -cne"), self.ps.index('Invoke-Plan $true'))
        self.assertNotRegex(self.sql, r'DECLARE @Nom\b')
        self.assertIn("$cmd.Parameters.Add('@'+$name", self.ps)

    def test_preflight_before_writes(self):
        self.assertLess(self.sql.index('Types, tailles'), self.sql.index('INSERT INTO TEST.'))
        self.assertIn('Correspondance HT/TTC non prouvee', self.sql)
        self.assertIn('@AllowDuplicates=0', self.sql)
        self.assertIn('OPENJSON(@ApprovedDuplicateCodes)', self.sql)

if __name__ == '__main__':
    unittest.main()
