SET NOCOUNT ON;SET XACT_ABORT ON;
DECLARE @Articles table(code nvarchar(40) PRIMARY KEY);
INSERT @Articles SELECT DISTINCT value FROM OPENJSON(@ArticlesJSON);
IF EXISTS(SELECT 1 FROM @Articles WHERE code NOT IN(N'CPJ35P',N'CPJ45')) THROW 63104,N'Articles hors correction F008.',1;
IF NOT EXISTS(SELECT 1 FROM TEST.BPSUPPLIER WHERE BPSNUM_0=N'F008') THROW 63105,N'F008 absent.',1;
IF EXISTS(SELECT 1 FROM @Articles A LEFT JOIN OB.ITMMASTER S ON S.ITMREF_0=A.code LEFT JOIN TEST.ITMMASTER T ON T.ITMREF_0=A.code WHERE S.ITMREF_0 IS NULL OR T.ITMREF_0 IS NULL OR S.ITMDES1_0<>T.ITMDES1_0 OR S.SAU_0<>T.SAU_0 OR S.STU_0<>T.STU_0 OR S.VACITM_0<>T.VACITM_0)
 THROW 63101,N'Identité article OB/TEST non concordante. Aucun rattachement effectué.',1;
IF EXISTS(SELECT 1 FROM @Articles A WHERE NOT EXISTS(SELECT 1 FROM OB.ITMBPS S WHERE S.ITMREF_0=A.code AND S.BPSNUM_0=N'F008'))
 THROW 63102,N'Paramétrage article-site source absent OB/201.',1;
DECLARE @Cols nvarchar(max),@SourceCols nvarchar(max),@Sql nvarchar(max),@Count int;
IF EXISTS(SELECT 1 FROM sys.columns T WHERE T.object_id=OBJECT_ID(N'TEST.ITMBPS') AND T.is_identity=0 AND T.is_computed=0 AND T.system_type_id<>189 AND NOT EXISTS(SELECT 1 FROM sys.columns S WHERE S.object_id=OBJECT_ID(N'OB.ITMBPS') AND S.name=T.name AND S.system_type_id=T.system_type_id AND S.max_length=T.max_length AND S.precision=T.precision AND S.scale=T.scale))
 THROW 63103,N'Schémas article-site incompatibles.',1;
SELECT @Cols=STRING_AGG(CONVERT(nvarchar(max),QUOTENAME(name)),N',') WITHIN GROUP(ORDER BY column_id),@SourceCols=STRING_AGG(CONVERT(nvarchar(max),N'S.'+QUOTENAME(name)),N',') WITHIN GROUP(ORDER BY column_id)
 FROM sys.columns WHERE object_id=OBJECT_ID(N'TEST.ITMBPS') AND is_identity=0 AND is_computed=0 AND system_type_id<>189;
BEGIN TRY
 BEGIN TRANSACTION;
 CREATE TABLE #Articles(code nvarchar(40) COLLATE DATABASE_DEFAULT PRIMARY KEY);
 INSERT #Articles SELECT code FROM @Articles;
 SET @Sql=N'INSERT TEST.ITMBPS ('+@Cols+N') SELECT '+@SourceCols+N' FROM OB.ITMBPS S JOIN #Articles A ON A.code=S.ITMREF_0 WHERE S.BPSNUM_0=N''F008'' AND NOT EXISTS(SELECT 1 FROM TEST.ITMBPS T WITH(UPDLOCK,HOLDLOCK) WHERE T.ITMREF_0=S.ITMREF_0 AND T.BPSNUM_0=S.BPSNUM_0); SET @Count=@@ROWCOUNT;';
 EXEC sys.sp_executesql @Sql,N'@Count int OUTPUT',@Count OUTPUT;
 IF @CommitCopy=1 COMMIT TRANSACTION;ELSE ROLLBACK TRANSACTION;
 SELECT N'ITMBPS' AS table_name,@Count AS inserted_rows,@CommitCopy AS committed;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;THROW;
END CATCH;
