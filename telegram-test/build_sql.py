"""One-time conversion of the SQL supplied by the user to a parameterized batch."""
from pathlib import Path
import re
import sys

# Historical importer predates the generalized customer/site/stock checks.
# Never overwrite the maintained execution batch with that old sample template.
if Path(__file__).with_name('sob-create.sql').exists():
    raise SystemExit('Import initial désactivé : sob-create.sql est maintenu directement et contient les corrections validées.')

source = Path(sys.argv[1]).read_text(encoding='utf-8-sig')
s = source[source.index('SET NOCOUNT ON;'):]
s = s.replace('SET XACT_ABORT ON;', 'SET XACT_ABORT ON;\nSET TRANSACTION ISOLATION LEVEL SERIALIZABLE;')
for name in ['AUTORISER_ECRITURE', 'TOTAL_TTC_ATTENDU', 'CLIENT', 'DATE', 'LIVRAISON', 'EXPEDITION', 'REFERENCE']:
    s = re.sub(r'^DECLARE @' + name + r'\b[^\n]*\n', '', s, flags=re.M)
for name, value in {
    'DEVISE': "nvarchar(6) = (SELECT CUR_0 FROM TEST.BPCUSTOMER WHERE BPCNUM_0=@CLIENT);",
    'NOM_REP': "nvarchar(100) = (SELECT R.REPNAM_0 FROM TEST.BPCUSTOMER C JOIN TEST.SALESREP R ON R.REPNUM_0=C.REP_0 WHERE C.BPCNUM_0=@CLIENT);",
    'ADRESSE': "nvarchar(10) = (SELECT BPAADD_0 FROM TEST.BPCUSTOMER WHERE BPCNUM_0=@CLIENT);",
    'COMMENTAIRE': "nvarchar(200) = N'SOB - commande validee depuis interface TEST';",
}.items():
    s = re.sub(r'DECLARE @' + name + r'\b[^\n]*', 'DECLARE @' + name + ' ' + value, s)
start = s.index('INSERT #L (LIGNE,ARTICLE,QTY,PRIX_TTC,FOURNISSEUR) VALUES')
end = s.index('\n\nDECLARE @REP', start)
s = s[:start] + """INSERT #L (LIGNE,ARTICLE,QTY,PRIX_TTC,FOURNISSEUR)
SELECT LIGNE,ARTICLE,QTY,PRIX_TTC,N''
FROM OPENJSON(@LINES_JSON) WITH (
 LIGNE int '$.line', ARTICLE nvarchar(40) '$.article',
 QTY decimal(18,5) '$.quantity', PRIX_TTC decimal(18,5) '$.price');
""" + s[end:]
s = s.replace(' BEGIN TRANSACTION;', """ BEGIN TRANSACTION;
 IF @CLIENT NOT IN(N'C01401',N'C10370') OR @DEVISE<>N'MAD'
    THROW 62002,N'Client non configure pour la creation ou devise incompatible.',1;
 IF NOT EXISTS(SELECT 1 FROM #L) OR (SELECT COUNT(*) FROM #L)>20
    THROW 62003,N'Nombre de lignes invalide.',1;
 UPDATE #L SET ARTICLE=N'MANTD',QTY=1 WHERE ARTICLE IN(N'TRS',N'TRC',N'MANTD');
 IF EXISTS(SELECT 1 FROM #L WHERE ARTICLE NOT IN(N'RAB10',N'RAB12',N'RAB16',N'RAB8',N'RAB14',N'RABT6',N'CPJ45',N'MANTD',N'PF-TP16X20',N'PF-TP08X20'))
    THROW 62004,N'Article hors perimetre de la requete testee.',1;
 IF @LIVRAISON<@DATE OR @EXPEDITION<>@LIVRAISON
    THROW 62005,N'Date de livraison invalide.',1;
 EXEC @LOCK=sys.sp_getapplock @Resource=@REFERENCE,
      @LockMode=N'Exclusive',@LockOwner=N'Transaction',@LockTimeout=10000;
 IF @LOCK<0 THROW 62006,N'Verrou de validation non obtenu.',1;
 IF @AUTORISER_ECRITURE=1 AND EXISTS(SELECT 1 FROM TEST.SORDER WHERE CUSORDREF_0=@REFERENCE)
 BEGIN
    IF (SELECT COUNT(*) FROM TEST.SORDER WHERE CUSORDREF_0=@REFERENCE)<>1
       THROW 62007,N'Reference ambigue : controle manuel necessaire.',1;
    IF NOT EXISTS(SELECT 1 FROM TEST.SORDER WHERE CUSORDREF_0=@REFERENCE AND BPCORD_0=@CLIENT)
       THROW 62007,N'Reference utilisee par un autre client.',1;
    SELECT TOP(1) N'ALREADY_CREATED' AS RESULTAT,SOHNUM_0 AS NUMERO_COMMANDE
    FROM TEST.SORDER WHERE CUSORDREF_0=@REFERENCE AND BPCORD_0=@CLIENT;
    COMMIT TRANSACTION;
    RETURN;
 END;
""", 1)
pos = s.index(' IF @AUTORISER_ECRITURE=0')
s = s[:pos] + """ DECLARE @PLAN nvarchar(max)=(SELECT
 @CLIENT AS client,@SOCIETE AS company,@SITE AS site,@TYPE AS order_type,
 @DATE AS order_date,@LIVRAISON AS delivery,@EXPEDITION AS shipment,
 @DEVISE AS currency,@REP AS rep,@ADRESSE AS address,
 @CLIENT_FACTURE AS invoice_client,@CLIENT_PAYEUR AS payer,@ADRESSE_PAYEUR AS payer_address,
 @BPCGRU AS customer_group,@MODE_FACTURATION AS billing_mode,@ORDCLE_INITIAL AS closed_state,
 @TOURNEE AS route,@PRIORITE_LIVRAISON AS delivery_priority,
 @TOTAL_HT AS ht,@TVA AS vat,@TOTAL_TTC AS ttc,
 JSON_QUERY((SELECT LIGNE,ARTICLE,QTY,PRIX_TTC,DESIGNATION,SAU,STU,COE,TAXE,PRIX_HT,DLVFLG
 FROM #L ORDER BY LIGNE FOR JSON PATH)) AS lines,
 JSON_QUERY((SELECT BPCNUM_0,BPCNAM_0,PTE_0,VACBPR_0 FROM TEST.BPCUSTOMER WHERE BPCNUM_0=@CLIENT FOR JSON PATH)) AS customer,
 JSON_QUERY((SELECT * FROM TEST.BPADDRESS WHERE BPANUM_0=@CLIENT AND BPAADD_0=@ADRESSE FOR JSON PATH)) AS address_details
 FOR JSON PATH,WITHOUT_ARRAY_WRAPPER);
 IF @AUTORISER_ECRITURE=1 AND (@EXPECTED_PLAN IS NULL OR CONVERT(varbinary(max),@EXPECTED_PLAN)<>CONVERT(varbinary(max),@PLAN))
   THROW 62008,N'Les donnees Sage ont change. Refaire le recapitulatif avant validation.',1;
 IF @AUTORISER_ECRITURE=0
 BEGIN
   SELECT N'PREVIEW' AS RESULTAT,@PLAN AS PLAN_JSON;
   ROLLBACK TRANSACTION;
   RETURN;
 END;
""" + s[pos:]
start = s.index('BEGIN CATCH')
end = s.index('END CATCH;', start)
s = s[:start] + 'BEGIN CATCH\n IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;\n THROW;\n' + s[end:]
pairs = sorted(set(re.findall(r"\(N'(SORDER|SORDERP|SORDERQ|SVCRVAT)',N'([^']+)',N'", s)))
values = ','.join("(N'%s',N'%s')" % pair for pair in pairs)
guard = """ IF EXISTS(SELECT 1 FROM (VALUES %s) M(TAB,COL)
 WHERE NOT EXISTS(SELECT 1 FROM sys.columns C
 WHERE C.object_id=OBJECT_ID(N'TEST.'+M.TAB) AND C.name=M.COL))
   THROW 62009,N'Une colonne requise est absente : controle du schema impossible.',1;
""" % values
s = s.replace(' DECLARE @PLAN nvarchar(max)=', guard + ' DECLARE @PLAN nvarchar(max)=')
header = '''/* SQL utilisateur du 08/11/2026, adapte pour parametres .NET.
   TEST uniquement, client C01401 / MAD / articles testes / T20 / annee 2026.
   Signature non geree et statuts repris de la requete fournie par l'utilisateur.
   Insertion directe : ne reproduit pas tous les traitements metier X3.
   Appels exclusivement via sob-execute.ps1, pas un script SSMS autonome.
*/
'''
Path(__file__).with_name('sob-create.sql').write_text(header + s, encoding='utf-8')

# Use the current customer billing mode rather than the original sample constant.
sql_path = Path(__file__).with_name('sob-create.sql')
current = sql_path.read_text(encoding='utf-8').replace('DECLARE @MODE_FACTURATION tinyint = 1; -- C01401 : valeur observee sur 14601', 'DECLARE @MODE_FACTURATION tinyint = (SELECT IME_0 FROM TEST.BPCUSTOMER WHERE BPCNUM_0=@CLIENT);').replace('@MODE_FACTURATION NOT IN(1,6)', '(@MODE_FACTURATION IS NULL OR @MODE_FACTURATION NOT IN(1,6))')
sql_path.write_text(current, encoding='utf-8')
