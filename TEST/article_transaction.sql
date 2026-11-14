-- Cloning logic adapted from the three supplied, validated scripts.
-- SqlClient supplies @Plan (JSON data only) and @Execute (bit). TEST only.
SET NOCOUNT ON; SET XACT_ABORT ON;
DECLARE @Resource nvarchar(20)=JSON_VALUE(@Plan,'$.resource'),@Code nvarchar(128)=JSON_VALUE(@Plan,'$.code');
DECLARE @Nodes table(n int PRIMARY KEY,tab sysname,model nvarchar(128),site nvarchar(30),supplier nvarchar(30),hash varchar(64),ov nvarchar(max));
DECLARE @Result table(n int,tab sysname,site nvarchar(30),supplier nvarchar(30),inserted int);
DECLARE @Deps table(tab sysname,model nvarchar(128),site nvarchar(30),hash varchar(64));
DECLARE @Lock int,@n int=1,@count int,@tab sysname,@model nvarchar(128),@site nvarchar(30),@supplier nvarchar(30),@hash varchar(64),@ov nvarchar(max),@sql nvarchar(max),@where nvarchar(max),@target nvarchar(max),@found int,@actual varchar(64),@cols nvarchar(max),@expr nvarchar(max),@unique nvarchar(max),@validate nvarchar(max),@message nvarchar(2048),@output nvarchar(max);
BEGIN TRY
 IF ISNULL(@Resource,'') NOT IN ('article','category') OR ISNULL(@Code,'')='' OR ISJSON(@Plan)<>1 OR ISNULL(JSON_VALUE(@Plan,'$.folder'),'')<>'TEST' THROW 50200,'Plan TEST invalide.',1;
 INSERT @Nodes SELECT CONVERT(int,[key])+1,JSON_VALUE(value,'$.table'),JSON_VALUE(value,'$.model'),JSON_VALUE(value,'$.site'),JSON_VALUE(value,'$.supplier'),JSON_VALUE(value,'$.source_hash'),JSON_QUERY(value,'$.overrides') FROM OPENJSON(@Plan,'$.nodes');
 IF (SELECT COUNT(*) FROM @Nodes) NOT BETWEEN 1 AND 50 OR EXISTS(SELECT 1 FROM @Nodes WHERE tab NOT IN ('ITMCATEG','ITMMASTER','ITMSALES','ITMFACILIT','ITMBPS','ATEXTRA') OR hash IS NULL OR ov IS NULL) THROW 50201,'Tables ou modeles non autorises.',1;
 IF @Resource='category' AND ((SELECT COUNT(*) FROM @Nodes)<>1 OR EXISTS(SELECT 1 FROM @Nodes WHERE tab<>'ITMCATEG')) THROW 50202,'Plan categorie invalide.',1;
 IF @Resource='article' AND ((SELECT COUNT(*) FROM @Nodes WHERE tab='ITMMASTER')<>1 OR (SELECT COUNT(*) FROM @Nodes WHERE tab='ATEXTRA')<>1 OR EXISTS(SELECT 1 FROM @Nodes WHERE tab='ITMCATEG')) THROW 50202,'Plan article incomplet.',1;
 BEGIN TRANSACTION;
 EXEC @Lock=sys.sp_getapplock @Resource='TEST_APPLICATION_CREATION_ARTICLE_CATEGORY',@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000;
 IF @Lock<0 THROW 50203,'Verrou indisponible.',1;
 IF @Resource='category' AND EXISTS(SELECT 1 FROM TEST.ITMCATEG WITH(UPDLOCK,HOLDLOCK) WHERE TCLCOD_0=@Code) THROW 50204,'Categorie deja existante.',1;
 IF @Resource='article' AND (EXISTS(SELECT 1 FROM TEST.ITMMASTER WITH(UPDLOCK,HOLDLOCK) WHERE ITMREF_0=@Code) OR EXISTS(SELECT 1 FROM TEST.ITMSALES WHERE ITMREF_0=@Code) OR EXISTS(SELECT 1 FROM TEST.ITMFACILIT WHERE ITMREF_0=@Code) OR EXISTS(SELECT 1 FROM TEST.ITMBPS WHERE ITMREF_0=@Code) OR EXISTS(SELECT 1 FROM TEST.ATEXTRA WHERE CODFIC_0='ITMMASTER' AND IDENT1_0=@Code)) THROW 50205,'Article ou dependance deja existant.',1;
 -- Category source is pinned too: a change between preview and confirmation rejects the write.
 INSERT @Deps SELECT JSON_VALUE(value,'$.table'),JSON_VALUE(value,'$.model'),JSON_VALUE(value,'$.site'),JSON_VALUE(value,'$.source_hash') FROM OPENJSON(@Plan,'$.dependencies');
 IF EXISTS(SELECT 1 FROM @Deps WHERE tab<>'ITMCATEG') THROW 50206,'Dependance non autorisee.',1;
 DECLARE dep CURSOR LOCAL FAST_FORWARD FOR SELECT model,site,hash FROM @Deps;
 OPEN dep; FETCH NEXT FROM dep INTO @model,@site,@hash;
 WHILE @@FETCH_STATUS=0 BEGIN
  SELECT @actual=CONVERT(varchar(64),HASHBYTES('SHA2_256',(SELECT c.* FOR JSON PATH,WITHOUT_ARRAY_WRAPPER)),2) FROM TEST.ITMCATEG c WITH(HOLDLOCK) WHERE TCLCOD_0=@model AND STOFCY_0=ISNULL(@site,'');
  IF @actual IS NULL OR @actual<>@hash THROW 50206,'Parametres categorie modifies depuis la preparation.',1;
  FETCH NEXT FROM dep INTO @model,@site,@hash;
 END; CLOSE dep; DEALLOCATE dep;
 IF NOT EXISTS(SELECT 1 FROM TEST.TABUNIT WHERE UOM_0=JSON_VALUE(@Plan,'$.unit')) THROW 50207,'Unite absente.',1;
 IF NOT EXISTS(SELECT 1 FROM TEST.GACCCODE WHERE TYP_0=1 AND ACCCOD_0=JSON_VALUE(@Plan,'$.accounting')) THROW 50208,'Code comptable absent.',1;
 IF NOT EXISTS(SELECT 1 FROM TEST.TABVACITM WHERE VACITM_0=JSON_VALUE(@Plan,'$.tax')) THROW 50209,'Niveau de taxe article absent.',1;
 SELECT @count=COUNT(*) FROM @Nodes;
 WHILE @n<=@count BEGIN
  SELECT @tab=tab,@model=model,@site=ISNULL(site,''),@supplier=ISNULL(supplier,''),@hash=hash,@ov=ov FROM @Nodes WHERE n=@n;
  IF OBJECT_ID('TEST.'+@tab,'U') IS NULL OR HAS_PERMS_BY_NAME('TEST.'+@tab,'OBJECT','SELECT')<>1 OR HAS_PERMS_BY_NAME('TEST.'+@tab,'OBJECT','INSERT')<>1 THROW 50210,'Table ou droits de lecture/insertion indisponibles.',1;
  IF EXISTS(SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('TEST.'+@tab) AND name='ROWID' AND is_identity=0 AND is_computed=0 AND default_object_id=0) THROW 50211,'ROWID non automatique.',1;
  IF EXISTS(SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('TEST.'+@tab) AND (is_disabled=1 OR is_not_trusted=1)) OR EXISTS(SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('TEST.'+@tab) AND (is_disabled=1 OR is_not_trusted=1)) THROW 50212,'Contraintes desactivees ou non fiables.',1;
  IF EXISTS(SELECT 1 FROM OPENJSON(@ov) j LEFT JOIN sys.columns c ON c.object_id=OBJECT_ID('TEST.'+@tab) AND c.name=j.[key] WHERE c.name IS NULL OR c.is_identity=1 OR c.is_computed=1 OR j.type IN (0,4,5) OR j.[key] LIKE '%[^A-Z0-9_]%' COLLATE Latin1_General_BIN2) THROW 50213,'Champ non reconnu ou valeur non scalaire.',1;
  SET @message=NULL;
  SELECT TOP(1) @message='Champ trop long : '+@tab+'.'+c.name FROM OPENJSON(@ov) j JOIN sys.columns c ON c.object_id=OBJECT_ID('TEST.'+@tab) AND c.name=j.[key]
  WHERE c.max_length<>-1 AND ((TYPE_NAME(c.system_type_id) IN ('nvarchar','nchar') AND DATALENGTH(j.value)>c.max_length) OR (TYPE_NAME(c.system_type_id) IN ('varchar','char') AND DATALENGTH(CONVERT(varchar(max),j.value))>c.max_length));
  IF @message IS NOT NULL THROW 50214,@message,1;
  IF @tab='ITMFACILIT' AND NOT EXISTS(SELECT 1 FROM TEST.FACILITY WHERE FCY_0=JSON_VALUE(@ov,'$.STOFCY_0')) THROW 50215,'Site demande absent.',1;
  IF @tab='ITMBPS' AND NOT EXISTS(SELECT 1 FROM TEST.BPSUPPLIER WHERE BPSNUM_0=JSON_VALUE(@ov,'$.BPSNUM_0')) THROW 50216,'Fournisseur absent.',1;
  SET @where=CASE @tab WHEN 'ITMCATEG' THEN N'SRC.TCLCOD_0=@Model AND SRC.STOFCY_0=''''' WHEN 'ITMFACILIT' THEN N'SRC.ITMREF_0=@Model AND SRC.STOFCY_0=@Site' WHEN 'ITMBPS' THEN N'SRC.ITMREF_0=@Model AND SRC.BPSNUM_0=@Supplier' WHEN 'ATEXTRA' THEN N'SRC.CODFIC_0=''ITMMASTER'' AND SRC.ZONE_0=''DES1AXX'' AND SRC.IDENT1_0=@Model AND SRC.LANGUE_0=''FRA''' ELSE N'SRC.ITMREF_0=@Model' END;
  SET @sql=N'SELECT @Found=COUNT(*) FROM TEST.'+QUOTENAME(@tab)+N' SRC WITH(HOLDLOCK) WHERE '+@where+N'; SELECT @Actual=CONVERT(varchar(64),HASHBYTES(''SHA2_256'',(SELECT SRC.* FOR JSON PATH,WITHOUT_ARRAY_WRAPPER)),2) FROM TEST.'+QUOTENAME(@tab)+N' SRC WITH(HOLDLOCK) WHERE '+@where+N';';
  SET @actual=NULL;SET @found=0;
  EXEC sys.sp_executesql @sql,N'@Model nvarchar(128),@Site nvarchar(30),@Supplier nvarchar(30),@Found int OUTPUT,@Actual varchar(64) OUTPUT',@model,@site,@supplier,@found OUTPUT,@actual OUTPUT;
  IF @found<>1 OR @actual<>@hash THROW 50217,'Modele absent, multiple ou modifie depuis la preparation.',1;
  -- Same STRING_AGG/QUOTENAME projection as the supplied scripts, with data-only overrides.
  SELECT @cols=STRING_AGG(CAST(QUOTENAME(c.name) AS nvarchar(max)),',') WITHIN GROUP(ORDER BY c.column_id),
   @expr=STRING_AGG(CAST(CASE WHEN j.[key] IS NOT NULL THEN
    'CONVERT('+QUOTENAME(TYPE_NAME(c.system_type_id))+CASE WHEN TYPE_NAME(c.system_type_id) IN ('nvarchar','nchar') THEN '('+CASE WHEN c.max_length=-1 THEN 'max' ELSE CONVERT(varchar(10),c.max_length/2) END+')' WHEN TYPE_NAME(c.system_type_id) IN ('varchar','char','binary','varbinary') THEN '('+CASE WHEN c.max_length=-1 THEN 'max' ELSE CONVERT(varchar(10),c.max_length) END+')' WHEN TYPE_NAME(c.system_type_id) IN ('decimal','numeric') THEN '('+CONVERT(varchar(10),c.precision)+','+CONVERT(varchar(10),c.scale)+')' ELSE '' END+',JSON_VALUE(@Overrides,''$.'+c.name+'''))'
    WHEN c.name='UPDTICK_0' THEN '1' WHEN c.name='AUUID_0' THEN 'CONVERT(binary(16),NEWID())' WHEN c.name IN ('CREUSR_0','UPDUSR_0') THEN 'N''ADMIN''' WHEN c.name IN ('CREDAT_0','UPDDAT_0','CREDATTIM_0','UPDDATTIM_0') THEN 'GETDATE()' ELSE 'SRC.'+QUOTENAME(c.name) END+' AS '+QUOTENAME(c.name) AS nvarchar(max)),',') WITHIN GROUP(ORDER BY c.column_id)
  FROM sys.columns c LEFT JOIN OPENJSON(@ov) j ON j.[key]=c.name
  WHERE c.object_id=OBJECT_ID('TEST.'+@tab) AND c.is_identity=0 AND c.is_computed=0 AND c.is_hidden=0 AND c.generated_always_type=0 AND c.system_type_id<>189 AND c.name<>'ROWID';
  IF @cols IS NULL OR @expr IS NULL THROW 50218,'Projection du modele impossible.',1;
  IF EXISTS(SELECT 1 FROM sys.indexes i WHERE i.object_id=OBJECT_ID('TEST.'+@tab) AND i.is_unique=1 AND i.has_filter=1) THROW 50219,'Index unique filtre : validation specifique requise.',1;
  SET @unique=N'';
  SELECT @unique=STRING_AGG(CAST(N'IF EXISTS(SELECT 1 FROM TEST.'+QUOTENAME(@tab)+N' D WITH(UPDLOCK,HOLDLOCK) CROSS JOIN #Candidate C WHERE '+q.condition+N') THROW 50220,''Cle unique deja utilisee.'',1;' AS nvarchar(max)),CHAR(10))
  FROM (SELECT i.index_id,STRING_AGG(CAST(N'(D.'+QUOTENAME(c.name)+N'=C.'+QUOTENAME(c.name)+N' OR (D.'+QUOTENAME(c.name)+N' IS NULL AND C.'+QUOTENAME(c.name)+N' IS NULL))' AS nvarchar(max)),' AND ') AS condition
    FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
    WHERE i.object_id=OBJECT_ID('TEST.'+@tab) AND i.is_unique=1 AND ic.key_ordinal>0 AND NOT EXISTS(SELECT 1 FROM sys.index_columns x JOIN sys.columns y ON y.object_id=x.object_id AND y.column_id=x.column_id WHERE x.object_id=i.object_id AND x.index_id=i.index_id AND (y.is_identity=1 OR y.name='ROWID')) GROUP BY i.index_id) q;
  SELECT @validate=STRING_AGG(CAST(N'IF EXISTS(SELECT 1 FROM #Candidate WHERE '+QUOTENAME(c.name)+N' IS NULL) THROW 50221,''Champ obligatoire absent.'',1;' AS nvarchar(max)),CHAR(10)) FROM sys.columns c WHERE c.object_id=OBJECT_ID('TEST.'+@tab) AND c.is_nullable=0 AND c.is_identity=0 AND c.is_computed=0 AND c.is_hidden=0 AND c.generated_always_type=0 AND c.system_type_id<>189 AND c.name<>'ROWID';
  SET @target=CASE @tab WHEN 'ITMCATEG' THEN N'D.TCLCOD_0=@Code AND D.STOFCY_0=''''' WHEN 'ITMFACILIT' THEN N'D.ITMREF_0=@Code AND D.STOFCY_0=JSON_VALUE(@Overrides,''$.STOFCY_0'')' WHEN 'ITMBPS' THEN N'D.ITMREF_0=@Code AND D.BPSNUM_0=JSON_VALUE(@Overrides,''$.BPSNUM_0'')' WHEN 'ATEXTRA' THEN N'D.CODFIC_0=''ITMMASTER'' AND D.ZONE_0=''DES1AXX'' AND D.IDENT1_0=@Code AND D.LANGUE_0=''FRA'' AND D.IDENT2_0=''''' ELSE N'D.ITMREF_0=@Code' END;
  SET @sql=N'SELECT '+@expr+N' INTO #Candidate FROM TEST.'+QUOTENAME(@tab)+N' SRC WHERE '+@where+N'; IF @@ROWCOUNT<>1 THROW 50222,''Projection multiple.'',1; '+ISNULL(@unique,'')+ISNULL(@validate,'')+N'
   IF @Apply=1 BEGIN INSERT INTO TEST.'+QUOTENAME(@tab)+N' ('+@cols+N') SELECT '+@cols+N' FROM #Candidate; IF @@ROWCOUNT<>1 THROW 50223,''Insertion incorrecte.'',1;
    IF (SELECT COUNT(*) FROM TEST.'+QUOTENAME(@tab)+N' D WHERE '+@target+N')<>1 THROW 50224,''Relecture cible absente ou multiple.'',1;
    IF EXISTS(SELECT '+@cols+N' FROM #Candidate EXCEPT SELECT '+@cols+N' FROM TEST.'+QUOTENAME(@tab)+N' D WHERE '+@target+N') THROW 50225,''Relecture differente de la ligne preparee.'',1;
   END;';
  EXEC sys.sp_executesql @sql,N'@Model nvarchar(128),@Site nvarchar(30),@Supplier nvarchar(30),@Overrides nvarchar(max),@Code nvarchar(128),@Apply bit',@model,@site,@supplier,@ov,@Code,@Execute;
  INSERT @Result VALUES(@n,@tab,JSON_VALUE(@ov,'$.STOFCY_0'),JSON_VALUE(@ov,'$.BPSNUM_0'),CONVERT(int,@Execute));
  SET @n=@n+1;
 END;
 IF @Execute=1 AND @Resource='article' BEGIN
  IF (SELECT COUNT(*) FROM TEST.ITMFACILIT WHERE ITMREF_0=@Code)<>(SELECT COUNT(*) FROM @Nodes WHERE tab='ITMFACILIT') THROW 50226,'Nombre de sites incorrect.',1;
  IF (SELECT COUNT(*) FROM TEST.ITMBPS WHERE ITMREF_0=@Code)<>(SELECT COUNT(*) FROM @Nodes WHERE tab='ITMBPS') THROW 50227,'Nombre de fournisseurs incorrect.',1;
  IF (SELECT COUNT(*) FROM TEST.ITMSALES WHERE ITMREF_0=@Code)<>(SELECT COUNT(*) FROM @Nodes WHERE tab='ITMSALES') THROW 50228,'Fiche vente incorrecte.',1;
  IF (SELECT COUNT(*) FROM TEST.ATEXTRA WHERE CODFIC_0='ITMMASTER' AND ZONE_0='DES1AXX' AND LANGUE_0='FRA' AND IDENT1_0=@Code AND IDENT2_0='')<>1 THROW 50229,'Traduction francaise incorrecte.',1;
 END;
 IF @Execute=1 COMMIT TRANSACTION; ELSE ROLLBACK TRANSACTION;
 SELECT @output=(SELECT CAST(1 AS bit) AS ok,'TEST' AS folder,@Resource AS resource,@Code AS code,@Execute AS executed,CASE WHEN @Execute=1 THEN 'COMMIT' ELSE 'VALIDATED_NO_INSERT' END AS transaction_state,JSON_QUERY((SELECT * FROM @Result ORDER BY n FOR JSON PATH)) AS records,CAST(@Execute AS bit) AS sql_verified FOR JSON PATH,WITHOUT_ARRAY_WRAPPER);
 SELECT @output;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
 SELECT @output=(SELECT CAST(0 AS bit) AS ok,'TEST' AS folder,ERROR_NUMBER() AS sql_error_number,CASE WHEN ERROR_NUMBER() BETWEEN 50200 AND 50229 THEN ERROR_MESSAGE() ELSE 'Insertion refusee par une contrainte SQL ; aucune nouvelle tentative automatique.' END AS message,'ROLLBACK' AS transaction_state,CAST(0 AS bit) AS executed FOR JSON PATH,WITHOUT_ARRAY_WRAPPER);
 SELECT @output;
END CATCH;
