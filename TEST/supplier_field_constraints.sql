-- Read-only metadata for the fields of the fixed supplier INSERT.
WITH fields(field,tab,col) AS (
 SELECT * FROM (VALUES
 ('Nom','BPARTNER','BPRNAM_0'),('Nom','BPSUPPLIER','BPSNAM_0'),
 ('NomCourt','BPARTNER','BPRSHO_0'),('NomCourt','BPSUPPLIER','BPSSHO_0'),
 ('ICE','BPARTNER','XICE_0'),('IF','BPARTNER','XIF_0'),('RC','BPARTNER','XRC_0'),
 ('Adresse','BPADDRESS','BPAADDLIG_0'),('Adresse2','BPADDRESS','BPAADDLIG_1'),('Adresse3','BPADDRESS','BPAADDLIG_2'),('Ville','BPADDRESS','CTY_0'),
 ('Telephone','BPADDRESS','TEL_0'),('Fax','BPADDRESS','FAX_0'),
 ('Paiement','BPSUPPLIER','PTE_0'),('Categorie','BPSUPPLIER','BSGCOD_0'),
 ('CodeComptable','BPSUPPLIER','ACCCOD_0'),('RegimeTaxe','BPSUPPLIER','VACBPR_0'),
 ('Devise','BPSUPPLIER','CUR_0')) v(field,tab,col)
)
SELECT f.field,f.tab,f.col,c.max_length,c.system_type_id,
 CASE WHEN c.max_length=-1 THEN -1 WHEN c.system_type_id IN (231,239) THEN c.max_length/2 ELSE c.max_length END AS max_characters,
 c.is_computed,c.is_identity
FROM fields f LEFT JOIN sys.columns c ON c.object_id=OBJECT_ID(N'TEST.'+f.tab) AND c.name=f.col;
