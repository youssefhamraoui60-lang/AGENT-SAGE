-- Only fixed, owner-confirmed application plans. Never arbitrary SQL; TEST only.
SET NOCOUNT ON;SET XACT_ABORT ON;
DECLARE @Out nvarchar(max),@DependencyJson nvarchar(max),@LockScan bit=1,@Lock int;
DECLARE @Nodes table(n int PRIMARY KEY,tab sysname,kind varchar(10),keys_json nvarchar(max),model_keys nvarchar(max),vals nvarchar(max),hash varchar(64));
DECLARE @Allowed table(tab sysname,cols nvarchar(1000),keys_list nvarchar(300),inserts bit);
INSERT @Allowed VALUES
 ('ITMMASTER','SALFLG_0,NEGSTO_0,ITMDES1_0,TCLCOD_0,ACCCOD_0,VACITM_0,VACITM_1,VACITM_2,STU_0,PUU_0,SAU_0,PUUSTUCOE_0,SAUSTUCOE_0,STOMGTCOD_0,ITMSTA_0,XFLGBPS_0,XBPS_0','ITMREF_0',0),
 ('ITMFACILIT','STOMGTCOD_0,STU_0,PUU_0,SAU_0','ITMREF_0,STOFCY_0',1),
 ('ITMSALES','ITMDES1_0','ITMREF_0',0),
 ('ITMBPS','ITMREFBPS_0,PUU_0,PUUSTUCOE_0','ITMREF_0,BPSNUM_0',1),
 ('ATEXTRA','TEXTE_0','CODFIC_0,ZONE_0,IDENT1_0,IDENT2_0,LANGUE_0',0),
 ('BPARTNER','ENAFLG_0,BPRNAM_0,BPRSHO_0,CNTNAM_0,XICE_0,XIF_0,XRC_0','BPRNUM_0',0),
 ('BPSUPPLIER','ENAFLG_0,BPSNAM_0,BPSSHO_0,CNTNAM_0,PTE_0','BPSNUM_0',0),
 ('BPADDRESS','BPAADDLIG_0,BPAADDLIG_1,BPAADDLIG_2,CTY_0,TEL_0,WEB_0','BPANUM_0,BPATYP_0,BPAADD_0',0),
 ('TABUNIT','UOMDEC_0,UOMSYM_0,UOMTYP_0,INTSAU_0','UOM_0',1),
 ('TABCOEFF','REV_0,COEUOM_0','UOM1_0,UOM2_0',1);
BEGIN TRY
 IF ISJSON(@Plan)<>1 OR ISNULL(JSON_VALUE(@Plan,'$.folder'),'')<>'TEST' OR JSON_VALUE(@Plan,'$.resource')<>@Resource OR JSON_VALUE(@Plan,'$.code')<>@Code OR @Resource NOT IN ('article','supplier','unit') THROW 50300,'Plan de modification TEST invalide.',1;
 INSERT @Nodes SELECT CONVERT(int,[key])+1,JSON_VALUE(value,'$.table'),JSON_VALUE(value,'$.kind'),JSON_QUERY(value,'$.keys'),JSON_QUERY(value,'$.model_keys'),JSON_QUERY(value,'$.values'),JSON_VALUE(value,'$.source_hash') FROM OPENJSON(@Plan,'$.nodes');
 IF (SELECT COUNT(*) FROM @Nodes) NOT BETWEEN 1 AND 40 OR EXISTS(SELECT 1 FROM @Nodes WHERE tab NOT IN (SELECT tab FROM @Allowed) OR kind NOT IN ('update','insert') OR keys_json IS NULL OR vals IS NULL OR hash IS NULL) THROW 50302,'Plan non autorise.',1;
 IF EXISTS(SELECT 1 FROM @Nodes WHERE (@Resource='article' AND tab NOT IN ('ITMMASTER','ITMFACILIT','ITMBPS','ITMSALES','ATEXTRA')) OR (@Resource='supplier' AND tab NOT IN ('BPARTNER','BPSUPPLIER','BPADDRESS')) OR (@Resource='unit' AND (tab NOT IN ('TABUNIT','TABCOEFF') OR kind<>'insert'))) THROW 50302,'Ressource et tables incompatibles.',1;
 BEGIN TRANSACTION;
 EXEC @Lock=sys.sp_getapplock @Resource='TEST_APPLICATION_MODIFICATION',@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000;
 IF @Lock<0 THROW 50303,'Verrou indisponible.',1;
 -- DEPENDENCY_SCAN_HERE
 IF @Resource<>'unit' AND (ISNULL(JSON_VALUE(@DependencyJson,'$.complete'),'false')<>'true' OR
 EXISTS(SELECT tab,has_matches,readable,columns_checked,active,activity_rule,evidence FROM @DepRows EXCEPT SELECT tab,has_matches,readable,columns_checked,active,activity_rule,evidence FROM OPENJSON(@Plan,'$.dependencies.sources') WITH(tab sysname,has_matches bit,readable bit,columns_checked nvarchar(max),active bit,activity_rule nvarchar(200),evidence nvarchar(max))) OR
 EXISTS(SELECT tab,has_matches,readable,columns_checked,active,activity_rule,evidence FROM OPENJSON(@Plan,'$.dependencies.sources') WITH(tab sysname,has_matches bit,readable bit,columns_checked nvarchar(max),active bit,activity_rule nvarchar(200),evidence nvarchar(max)) EXCEPT SELECT tab,has_matches,readable,columns_checked,active,activity_rule,evidence FROM @DepRows)) THROW 50304,'Dependances modifiees ou analyse incomplete : repreparez la modification.',1;
 IF @Resource='supplier' AND EXISTS(SELECT 1 FROM @Nodes WHERE JSON_VALUE(vals,'$.ENAFLG_0') IS NOT NULL)
 BEGIN
  IF (SELECT COUNT(*) FROM @Nodes WHERE tab IN ('BPARTNER','BPSUPPLIER') AND JSON_VALUE(vals,'$.ENAFLG_0') IN ('1','2'))<>2
     OR (SELECT COUNT(DISTINCT JSON_VALUE(vals,'$.ENAFLG_0')) FROM @Nodes WHERE tab IN ('BPARTNER','BPSUPPLIER'))<>1
     THROW 50302,'Statuts tiers et fournisseur incoherents.',1;
  IF EXISTS(SELECT 1 FROM @DepRows WHERE has_matches=1 AND tab NOT IN ('BPARTNER','BPSUPPLIER','BPADDRESS','CONTACT','CONTACTCRM','ITMBPS','ITMMASTER') AND (active=1 OR active IS NULL))
     THROW 50304,'Operations actives ou cloture non demontree : statut bloque.',1;
  IF EXISTS(SELECT 1 FROM (VALUES('BPARTNER'),('BPSUPPLIER')) t(tab)
     WHERE NOT EXISTS(SELECT 1 FROM TEST.ATABZON z JOIN TEST.APLSTD l ON l.LANCHP_0=z.NOLIB_0 AND l.LAN_0='FRA'
       WHERE z.CODFIC_0=t.tab AND z.CODZONE_0='ENAFLG' AND l.LANNUM_0=1 AND LTRIM(RTRIM(l.LANMES_0)) COLLATE Latin1_General_CI_AI IN (N'Non',N'Inactif',N'Desactive'))
        OR NOT EXISTS(SELECT 1 FROM TEST.ATABZON z JOIN TEST.APLSTD l ON l.LANCHP_0=z.NOLIB_0 AND l.LAN_0='FRA'
       WHERE z.CODFIC_0=t.tab AND z.CODZONE_0='ENAFLG' AND l.LANNUM_0=2 AND LTRIM(RTRIM(l.LANMES_0)) COLLATE Latin1_General_CI_AI IN (N'Oui',N'Actif',N'Active')))
     THROW 50302,'Menu de statut Sage non verifie.',1;
 END;
 IF @Resource='article' AND EXISTS(SELECT 1 FROM @Nodes n CROSS APPLY OPENJSON(n.vals) f WHERE n.tab='ITMMASTER' AND f.[key] IN ('NEGSTO_0','XFLGBPS_0') AND
   (f.value NOT IN ('1','2') OR NOT EXISTS(SELECT 1 FROM TEST.ATABZON z JOIN TEST.APLSTD l ON l.LANCHP_0=z.NOLIB_0 AND l.LAN_0='FRA' WHERE z.CODFIC_0='ITMMASTER' AND z.CODZONE_0=LEFT(f.[key],LEN(f.[key])-2) AND l.LANNUM_0=1 AND LTRIM(RTRIM(l.LANMES_0)) COLLATE Latin1_General_CI_AI=N'Non')
    OR NOT EXISTS(SELECT 1 FROM TEST.ATABZON z JOIN TEST.APLSTD l ON l.LANCHP_0=z.NOLIB_0 AND l.LAN_0='FRA' WHERE z.CODFIC_0='ITMMASTER' AND z.CODZONE_0=LEFT(f.[key],LEN(f.[key])-2) AND l.LANNUM_0=2 AND LTRIM(RTRIM(l.LANMES_0)) COLLATE Latin1_General_CI_AI=N'Oui')))
    THROW 50302,'Indicateur article ou menu Sage non verifie.',1;
 DECLARE @tab sysname,@kind varchar(10),@keys nvarchar(max),@modelKeys nvarchar(max),@vals nvarchar(max),@hash varchar(64),@where nvarchar(max),@modelWhere nvarchar(max),@sql nvarchar(max),@actual varchar(64),@found int,@n int=1,@count int=(SELECT COUNT(*) FROM @Nodes),@cols nvarchar(max),@expr nvarchar(max),@set nvarchar(max),@unique nvarchar(max),@compare nvarchar(max),@versionCheck nvarchar(max),@keylist nvarchar(300),@allowedcols nvarchar(1000),@inserts bit,@affected int=0;
 -- Pin all referenced master/configuration records; no history tables can be written.
 DECLARE guards CURSOR LOCAL FAST_FORWARD FOR SELECT JSON_VALUE(value,'$.table'),JSON_QUERY(value,'$.keys'),JSON_VALUE(value,'$.source_hash') FROM OPENJSON(@Plan,'$.guards');
 OPEN guards;FETCH NEXT FROM guards INTO @tab,@keys,@hash;
 WHILE @@FETCH_STATUS=0 BEGIN
  IF @tab NOT IN ('ITMMASTER','BPSUPPLIER','ITMCATEG','GACCCODE','TABVACITM','TABVAT','TABVAC','TABUNIT','TABCOEFF','TABPAYTERM') OR EXISTS(SELECT 1 FROM OPENJSON(@keys) j LEFT JOIN sys.columns c ON c.object_id=OBJECT_ID('TEST.'+@tab) AND c.name=j.[key] WHERE c.name IS NULL OR j.type IN(0,4,5) OR j.[key] LIKE '%[^A-Z0-9_]%' COLLATE Latin1_General_BIN2) THROW 50305,'Garde de lecture invalide.',1;
  SELECT @where=STRING_AGG(CONVERT(nvarchar(max),'SRC.'+QUOTENAME([key])+'=JSON_VALUE(@Keys,''$.'+[key]+''')'),' AND ') FROM OPENJSON(@keys);
  SET @sql=N'SELECT @Found=COUNT(*) FROM TEST.'+QUOTENAME(@tab)+N' SRC WITH(HOLDLOCK) WHERE '+@where+N'; SELECT @Actual=CONVERT(varchar(64),HASHBYTES(''SHA2_256'',(SELECT SRC.* FOR JSON PATH,WITHOUT_ARRAY_WRAPPER)),2) FROM TEST.'+QUOTENAME(@tab)+N' SRC WITH(HOLDLOCK) WHERE '+@where+N';';
  SET @actual=NULL;SET @found=0;EXEC sys.sp_executesql @sql,N'@Keys nvarchar(max),@Found int OUTPUT,@Actual varchar(64) OUTPUT',@keys,@found OUTPUT,@actual OUTPUT;
  IF @found<>1 OR ISNULL(@actual,'')<>@hash THROW 50306,'Un referentiel ou la fiche a change depuis la preparation.',1;
  FETCH NEXT FROM guards INTO @tab,@keys,@hash;
 END;CLOSE guards;DEALLOCATE guards;
 DECLARE @Results table(n int,tab sysname,kind varchar(10),affected int);
 WHILE @n<=@count BEGIN
  SELECT @tab=tab,@kind=kind,@keys=keys_json,@modelKeys=model_keys,@vals=vals,@hash=hash FROM @Nodes WHERE n=@n;
  SELECT @keylist=keys_list,@allowedcols=cols,@inserts=inserts FROM @Allowed WHERE tab=@tab;
  IF @kind='insert' AND @inserts<>1 THROW 50307,'Insertion non autorisee pour cette table.',1;
  IF @kind='update' AND @tab IN ('TABUNIT','TABCOEFF') THROW 50307,'Unites existantes immuables dans ce service.',1;
  IF HAS_PERMS_BY_NAME('TEST.'+@tab,'OBJECT','SELECT')<>1 OR HAS_PERMS_BY_NAME('TEST.'+@tab,'OBJECT',CASE WHEN @kind='update' THEN 'UPDATE' ELSE 'INSERT' END)<>1 THROW 50308,'Permission necessaire manquante.',1;
  IF EXISTS(SELECT 1 FROM OPENJSON(@keys) WHERE CHARINDEX(','+[key]+',',','+@keylist+',')=0 OR type IN(0,4,5)) OR (SELECT COUNT(*) FROM OPENJSON(@keys))<>(SELECT COUNT(*) FROM STRING_SPLIT(@keylist,',')) THROW 50309,'Cles invalides.',1;
  IF EXISTS(SELECT 1 FROM OPENJSON(@vals) j LEFT JOIN sys.columns c ON c.object_id=OBJECT_ID('TEST.'+@tab) AND c.name=j.[key] WHERE c.name IS NULL OR c.is_identity=1 OR c.is_computed=1 OR j.type IN(0,4,5) OR CHARINDEX(','+j.[key]+',',','+@allowedcols+CASE WHEN @kind='insert' THEN ','+@keylist ELSE '' END+',')=0) THROW 50310,'Champ interdit ou absent.',1;
  IF EXISTS(SELECT 1 FROM OPENJSON(@vals) j WHERE CHARINDEX(','+j.[key]+',',','+@keylist+',')>0 AND @kind='update') THROW 50311,'Modification de code ou de cle interdite.',1;
  IF (@Resource='article' AND ((@tab='ATEXTRA' AND (JSON_VALUE(@keys,'$.IDENT1_0')<>@Code OR JSON_VALUE(@keys,'$.CODFIC_0')<>'ITMMASTER' OR JSON_VALUE(@keys,'$.ZONE_0')<>'DES1AXX' OR JSON_VALUE(@keys,'$.LANGUE_0')<>'FRA' OR JSON_VALUE(@keys,'$.IDENT2_0')<>'')) OR (@tab<>'ATEXTRA' AND JSON_VALUE(@keys,'$.ITMREF_0')<>@Code))) OR
     (@Resource='supplier' AND ((@tab='BPSUPPLIER' AND JSON_VALUE(@keys,'$.BPSNUM_0')<>@Code) OR (@tab='BPARTNER' AND JSON_VALUE(@keys,'$.BPRNUM_0')<>@Code) OR (@tab='BPADDRESS' AND (JSON_VALUE(@keys,'$.BPANUM_0')<>@Code OR JSON_VALUE(@keys,'$.BPATYP_0')<>'1')))) OR
     (@Resource='unit' AND ((@tab='TABUNIT' AND JSON_VALUE(@keys,'$.UOM_0')<>@Code) OR (@tab='TABCOEFF' AND JSON_VALUE(@keys,'$.UOM1_0')<>@Code AND JSON_VALUE(@keys,'$.UOM2_0')<>@Code))) THROW 50312,'Cible hors de la fiche confirmee.',1;
  IF EXISTS(SELECT 1 FROM sys.triggers tr WHERE tr.parent_id=OBJECT_ID('TEST.'+@tab) AND tr.is_disabled=0 AND NOT EXISTS(SELECT 1 FROM OPENJSON(@Plan,'$.triggers') WITH(tab sysname '$.table',name sysname,hash varchar(64)) p WHERE p.tab=@tab AND p.name=tr.name AND p.hash=CONVERT(varchar(64),HASHBYTES('SHA2_256',OBJECT_DEFINITION(tr.object_id)),2))) THROW 50313,'Declencheur non verifie ou modifie.',1;
  IF EXISTS(SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('TEST.'+@tab) AND (is_disabled=1 OR is_not_trusted=1)) OR EXISTS(SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('TEST.'+@tab) AND (is_disabled=1 OR is_not_trusted=1)) THROW 50314,'Contraintes non fiables.',1;
  IF EXISTS(SELECT 1 FROM OPENJSON(@vals) j JOIN sys.columns c ON c.object_id=OBJECT_ID('TEST.'+@tab) AND c.name=j.[key] WHERE c.max_length<>-1 AND ((TYPE_NAME(c.system_type_id) IN ('nvarchar','nchar') AND DATALENGTH(j.value)>c.max_length) OR (TYPE_NAME(c.system_type_id) IN ('varchar','char') AND DATALENGTH(CONVERT(varchar(max),j.value))>c.max_length))) THROW 50315,'Champ trop long : aucune troncature autorisee.',1;
  IF @tab='ITMMASTER' AND EXISTS(SELECT 1 FROM OPENJSON(@vals) WHERE [key] LIKE 'VACITM[_]%' AND NOT EXISTS(SELECT 1 FROM TEST.TABVACITM t WHERE t.VACITM_0=value AND t.ENAFLG_0=2)) THROW 50316,'Niveau de taxe absent ou inactif.',1;
  IF @tab='ITMMASTER' AND JSON_VALUE(@vals,'$.ACCCOD_0') IS NOT NULL AND NOT EXISTS(SELECT 1 FROM TEST.GACCCODE WHERE TYP_0=1 AND ACCCOD_0=JSON_VALUE(@vals,'$.ACCCOD_0')) THROW 50316,'Code comptable invalide.',1;
  IF @tab='ITMMASTER' AND JSON_VALUE(@vals,'$.XBPS_0') IS NOT NULL AND NOT EXISTS(SELECT 1 FROM TEST.BPSUPPLIER WHERE BPSNUM_0=JSON_VALUE(@vals,'$.XBPS_0') AND ENAFLG_0=2) THROW 50316,'Fournisseur principal absent ou inactif.',1;
  IF @tab='ITMBPS' AND NOT EXISTS(SELECT 1 FROM TEST.BPSUPPLIER WHERE BPSNUM_0=JSON_VALUE(@keys,'$.BPSNUM_0') AND ENAFLG_0=2) THROW 50316,'Fournisseur absent ou inactif.',1;
  IF @tab='BPSUPPLIER' AND JSON_VALUE(@vals,'$.PTE_0') IS NOT NULL AND NOT EXISTS(SELECT 1 FROM TEST.TABPAYTERM WHERE PTE_0=JSON_VALUE(@vals,'$.PTE_0')) THROW 50316,'Conditions de paiement inconnues.',1;
  IF @tab='BPARTNER' AND EXISTS(SELECT 1 FROM TEST.BPARTNER WITH(UPDLOCK,HOLDLOCK) WHERE BPRNUM_0<>@Code AND ((ISNULL(JSON_VALUE(@vals,'$.XICE_0'),'')<>'' AND XICE_0=JSON_VALUE(@vals,'$.XICE_0')) OR (ISNULL(JSON_VALUE(@vals,'$.XIF_0'),'')<>'' AND XIF_0=JSON_VALUE(@vals,'$.XIF_0')) OR (ISNULL(JSON_VALUE(@vals,'$.XRC_0'),'')<>'' AND XRC_0=JSON_VALUE(@vals,'$.XRC_0')))) THROW 50317,'Identifiant fiscal deja utilise par un autre tiers.',1;
  SELECT @where=STRING_AGG(CONVERT(nvarchar(max),'D.'+QUOTENAME([key])+'=JSON_VALUE(@Keys,''$.'+[key]+''')'),' AND ') FROM OPENJSON(@keys);
  IF @kind='insert' BEGIN
   IF @modelKeys IS NULL OR EXISTS(SELECT 1 FROM OPENJSON(@modelKeys) WHERE CHARINDEX(','+[key]+',',','+@keylist+',')=0 OR type IN(0,4,5)) OR (SELECT COUNT(*) FROM OPENJSON(@modelKeys))<>(SELECT COUNT(*) FROM STRING_SPLIT(@keylist,',')) THROW 50318,'Cles modele invalides.',1;
   SELECT @modelWhere=STRING_AGG(CONVERT(nvarchar(max),'SRC.'+QUOTENAME([key])+'=JSON_VALUE(@ModelKeys,''$.'+[key]+''')'),' AND ') FROM OPENJSON(@modelKeys);
   IF EXISTS(SELECT 1 FROM OPENJSON(@keys) k WHERE ISNULL(JSON_VALUE(@vals,'$.'+k.[key]),CHAR(1))<>k.value) THROW 50318,'Cles de projection incoherentes.',1;
  END ELSE SET @modelWhere=REPLACE(@where,'D.','SRC.');
  SET @sql=N'SELECT @Found=COUNT(*) FROM TEST.'+QUOTENAME(@tab)+N' SRC WITH(UPDLOCK,HOLDLOCK) WHERE '+@modelWhere+N'; SELECT @Actual=CONVERT(varchar(64),HASHBYTES(''SHA2_256'',(SELECT SRC.* FOR JSON PATH,WITHOUT_ARRAY_WRAPPER)),2) FROM TEST.'+QUOTENAME(@tab)+N' SRC WITH(UPDLOCK,HOLDLOCK) WHERE '+@modelWhere+N';';
  SET @actual=NULL;SET @found=0;EXEC sys.sp_executesql @sql,N'@Keys nvarchar(max),@ModelKeys nvarchar(max),@Found int OUTPUT,@Actual varchar(64) OUTPUT',@keys,@modelKeys,@found OUTPUT,@actual OUTPUT;
  IF @found<>1 OR ISNULL(@actual,'')<>@hash THROW 50319,'Ligne absente, multiple ou modifiee depuis la preparation.',1;
  -- Same typed projection strategy as validated creation, without changing any key on UPDATE.
  SELECT @cols=STRING_AGG(CONVERT(nvarchar(max),QUOTENAME(c.name)),',') WITHIN GROUP(ORDER BY c.column_id),
   @expr=STRING_AGG(CONVERT(nvarchar(max),CASE WHEN j.[key] IS NOT NULL THEN 'CONVERT('+QUOTENAME(TYPE_NAME(c.system_type_id))+CASE WHEN TYPE_NAME(c.system_type_id) IN ('nvarchar','nchar') THEN '('+CASE WHEN c.max_length=-1 THEN 'max' ELSE CONVERT(varchar(10),c.max_length/2) END+')' WHEN TYPE_NAME(c.system_type_id) IN ('varchar','char','varbinary','binary') THEN '('+CASE WHEN c.max_length=-1 THEN 'max' ELSE CONVERT(varchar(10),c.max_length) END+')' WHEN TYPE_NAME(c.system_type_id) IN ('numeric','decimal') THEN '('+CONVERT(varchar(10),c.precision)+','+CONVERT(varchar(10),c.scale)+')' ELSE '' END+',JSON_VALUE(@Values,''$.'+c.name+'''))'
    WHEN c.name='UPDTICK_0' THEN CASE WHEN @kind='insert' THEN '1' ELSE 'SRC.UPDTICK_0+1' END WHEN c.name='AUUID_0' AND @kind='insert' THEN 'CONVERT(binary(16),NEWID())' WHEN c.name='UPDUSR_0' OR (c.name='CREUSR_0' AND @kind='insert') THEN 'N''ADMIN''' WHEN c.name IN ('UPDDAT_0','UPDDATTIM_0') OR (c.name IN ('CREDAT_0','CREDATTIM_0') AND @kind='insert') THEN 'GETDATE()' ELSE 'SRC.'+QUOTENAME(c.name) END+' AS '+QUOTENAME(c.name)),',') WITHIN GROUP(ORDER BY c.column_id)
  FROM sys.columns c LEFT JOIN OPENJSON(@vals) j ON j.[key]=c.name WHERE c.object_id=OBJECT_ID('TEST.'+@tab) AND c.is_identity=0 AND c.is_computed=0 AND c.is_hidden=0 AND c.generated_always_type=0 AND c.system_type_id<>189 AND c.name<>'ROWID';
  IF EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('TEST.'+@tab) AND is_unique=1 AND has_filter=1) THROW 50320,'Index filtre : validation specifique requise.',1;
  SELECT @unique=STRING_AGG(CONVERT(nvarchar(max),'IF EXISTS(SELECT 1 FROM TEST.'+QUOTENAME(@tab)+' D WITH(UPDLOCK,HOLDLOCK) CROSS JOIN #Candidate C WHERE '+u.condition+CASE WHEN @kind='update' THEN ' AND NOT('+@where+')' ELSE '' END+') THROW 50321,''Cle unique deja utilisee.'',1;'),CHAR(10)) FROM
  (SELECT i.index_id,STRING_AGG(CONVERT(nvarchar(max),'(D.'+QUOTENAME(c.name)+'=C.'+QUOTENAME(c.name)+' OR (D.'+QUOTENAME(c.name)+' IS NULL AND C.'+QUOTENAME(c.name)+' IS NULL))'),' AND ') AS condition FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id WHERE i.object_id=OBJECT_ID('TEST.'+@tab) AND i.is_unique=1 AND ic.key_ordinal>0 AND NOT EXISTS(SELECT 1 FROM sys.index_columns x JOIN sys.columns y ON y.object_id=x.object_id AND y.column_id=x.column_id WHERE x.object_id=i.object_id AND x.index_id=i.index_id AND (y.is_identity=1 OR y.name='ROWID')) GROUP BY i.index_id) u;
  SELECT @set=STRING_AGG(CONVERT(nvarchar(max),QUOTENAME(c.name)+'=C.'+QUOTENAME(c.name)),',') FROM sys.columns c WHERE c.object_id=OBJECT_ID('TEST.'+@tab) AND (EXISTS(SELECT 1 FROM OPENJSON(@vals) WHERE [key]=c.name) OR c.name IN ('UPDTICK_0','UPDUSR_0','UPDDAT_0','UPDDATTIM_0'));
  SELECT @compare=STRING_AGG(CONVERT(nvarchar(max),QUOTENAME(c.name)),',') WITHIN GROUP(ORDER BY c.column_id) FROM sys.columns c WHERE c.object_id=OBJECT_ID('TEST.'+@tab) AND c.is_identity=0 AND c.is_computed=0 AND c.is_hidden=0 AND c.generated_always_type=0 AND c.system_type_id<>189 AND c.name NOT IN ('ROWID','UPDTICK_0','UPDUSR_0','UPDDAT_0','UPDDATTIM_0');
  SET @versionCheck=CASE WHEN @kind='update' AND COL_LENGTH('TEST.'+@tab,'UPDTICK_0') IS NOT NULL THEN N' IF EXISTS(SELECT 1 FROM TEST.'+QUOTENAME(@tab)+N' D CROSS JOIN #Candidate C WHERE '+@where+N' AND (D.UPDTICK_0 IS NULL OR D.UPDTICK_0<C.UPDTICK_0)) THROW 50325,''Compteur de version non incremente.'',1;' ELSE N'' END;
  SET @sql=N'SELECT '+@expr+N' INTO #Candidate FROM TEST.'+QUOTENAME(@tab)+N' SRC WHERE '+@modelWhere+N'; IF @@ROWCOUNT<>1 THROW 50322,''Projection non unique.'',1; '+ISNULL(@unique,'')+N' IF @Apply=1 BEGIN '+CASE WHEN @kind='insert' THEN N'INSERT INTO TEST.'+QUOTENAME(@tab)+N'('+@cols+N') SELECT '+@cols+N' FROM #Candidate;' ELSE N'UPDATE D SET '+@set+N' FROM TEST.'+QUOTENAME(@tab)+N' D CROSS JOIN #Candidate C WHERE '+@where+N';' END+N' IF @@ROWCOUNT<>1 THROW 50323,''Nombre de lignes modifiees incorrect.'',1; IF (SELECT COUNT(*) FROM TEST.'+QUOTENAME(@tab)+N' D WHERE '+@where+N')<>1 THROW 50324,''Relecture absente ou multiple.'',1; IF EXISTS(SELECT '+@compare+N' FROM #Candidate EXCEPT SELECT '+@compare+N' FROM TEST.'+QUOTENAME(@tab)+N' D WHERE '+@where+N') THROW 50325,''Relecture differente ou modification metier non demandee.'',1; '+@versionCheck+N' END;';
  EXEC sys.sp_executesql @sql,N'@Keys nvarchar(max),@ModelKeys nvarchar(max),@Values nvarchar(max),@Apply bit',@keys,@modelKeys,@vals,@Execute;
  INSERT @Results VALUES(@n,@tab,@kind,CONVERT(int,@Execute));SET @affected=@affected+CONVERT(int,@Execute);SET @n=@n+1;
 END;
 IF @Execute=1 AND @Resource='article' AND EXISTS(SELECT 1 FROM @Nodes WHERE tab='ITMMASTER' AND JSON_VALUE(vals,'$.XBPS_0') IS NOT NULL) AND NOT EXISTS(SELECT 1 FROM TEST.ITMMASTER m JOIN TEST.ITMBPS l ON l.ITMREF_0=m.ITMREF_0 AND l.BPSNUM_0=m.XBPS_0 JOIN TEST.BPSUPPLIER p ON p.BPSNUM_0=m.XBPS_0 WHERE m.ITMREF_0=@Code AND m.XFLGBPS_0=2) THROW 50325,'Fournisseur principal non reference apres modification.',1;
 IF @Execute=1 COMMIT TRANSACTION;ELSE ROLLBACK TRANSACTION;
 SELECT @Out=(SELECT CAST(1 AS bit) AS ok,'TEST' AS folder,@Resource AS resource,@Code AS code,@Execute AS executed,CAST(@Execute AS bit) AS verified,@affected AS affected,CASE WHEN @Execute=1 THEN 'COMMIT' ELSE 'VALIDATED_NO_WRITE' END AS transaction_state,JSON_QUERY((SELECT * FROM @Results ORDER BY n FOR JSON PATH)) AS records FOR JSON PATH,WITHOUT_ARRAY_WRAPPER);SELECT @Out;
END TRY BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
 SELECT @Out=(SELECT CAST(0 AS bit) AS ok,'TEST' AS folder,CAST(0 AS bit) AS executed,ERROR_NUMBER() AS sql_error_number,'ROLLBACK' AS transaction_state,CASE WHEN ERROR_NUMBER() BETWEEN 50300 AND 50325 THEN ERROR_MESSAGE() ELSE 'Modification refusee par SQL ; aucun renvoi automatique.' END AS message FOR JSON PATH,WITHOUT_ARRAY_WRAPPER);SELECT @Out;
END CATCH;
