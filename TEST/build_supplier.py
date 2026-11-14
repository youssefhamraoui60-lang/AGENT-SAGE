"""Build the TEST-only parameterized version of the supplied Sage SQL."""
from pathlib import Path
import re

ROOT = Path(__file__).parent
source = (ROOT / 'supplier_original.sql').read_text(encoding='utf-8-sig')
source = re.sub(r'USE \[x3v12\];\s*GO', '', source, count=1)
source = re.sub(r'DECLARE @(Nom|NomCourt|ICE|IF|RC|DateRegularite|Adresse|Ville|Telephone|Fax|Paiement|Categorie|CodeComptable|RegimeTaxe|Devise|TypeMontant|CodeModele)\b[^;]*;', '', source)
preflight = (ROOT / 'preflight.sql').read_text(encoding='utf-8')
source = source.replace("IF LEN(@ICE) <> 15\n       OR @ICE LIKE '%[^0-9]%'", "IF @ICE <> N'' AND (LEN(@ICE) <> 15\n       OR @ICE LIKE '%[^0-9]%')", 1)
source = source.replace('BEGIN TRANSACTION;', 'BEGIN TRANSACTION;\n' + preflight, 1)
source = source.replace('BEGIN TRY', "IF @@TRANCOUNT <> 0 THROW 50112, 'Transaction externe interdite.', 1;\nBEGIN TRY", 1)
source = source.replace("BPR.BPRNUM_0 AS CODE_FOURNISSEUR,", "BPR.BPRNUM_0 AS CODE_FOURNISSEUR,\n        BPR.ENAFLG_0 AS partner_active, BPS.ENAFLG_0 AS supplier_active,\n        BPR.CRY_0 AS PAYS, BPR.BPRSHO_0 AS NOM_COURT,")
source = source.replace("        'ROLLBACK' AS ETAT_TRANSACTION;", "        'ROLLBACK' AS ETAT_TRANSACTION;\n    THROW;")
# Preview performs the same preflight, without running any INSERT.
source = source.replace('    DECLARE CurTables CURSOR', "    IF @Execute = 0\n    BEGIN\n        ROLLBACK TRANSACTION;\n        SELECT @NouveauCode AS CODE_PROPOSE_NON_RESERVE, N'VALIDATED_NO_INSERT' AS RESULTAT;\n        RETURN;\n    END;\n\n    DECLARE CurTables CURSOR", 1)
source = "-- Generated from the supplied SQL. Only TEST is writable. Parameters supplied by SqlClient.\n" + source
(ROOT / 'create_supplier.sql').write_text(source, encoding='utf-8')
