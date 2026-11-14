SET NOCOUNT ON; SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
DECLARE @Clients table(code nvarchar(40) PRIMARY KEY);
INSERT @Clients SELECT DISTINCT value FROM OPENJSON(@ArticlesJSON);
IF EXISTS(SELECT 1 FROM @Clients C WHERE NOT EXISTS(SELECT 1 FROM OB.ITMMASTER S WHERE S.ITMREF_0=C.code)) THROW 63110,'Article source absent.',1;
IF EXISTS(SELECT 1 FROM @Clients C JOIN OB.ITMMASTER S ON S.ITMREF_0=C.code JOIN TEST.ITMMASTER T ON T.ITMREF_0=C.code WHERE S.ITMDES1_0<>T.ITMDES1_0 OR S.SAU_0<>T.SAU_0 OR S.STU_0<>T.STU_0 OR S.VACITM_0<>T.VACITM_0) THROW 63111,'Identite article existant differente, aucune copie.',1;
IF EXISTS(SELECT 1 FROM OB.ITMMASTER S JOIN @Clients C ON C.code=S.ITMREF_0 WHERE DATALENGTH(S.XITMREF_0)>COL_LENGTH(N'TEST.ITMMASTER',N'XITMREF_0')) THROW 63113,'Reference XITMREF trop longue dans TEST : aucune troncature permise.',1;
DECLARE @CopyLog table(table_name sysname,inserted_rows int);
BEGIN TRY
 BEGIN TRANSACTION;
 DECLARE @Lock int;
 EXEC @Lock=sys.sp_getapplock @Resource=N'SOB_TEST_MASTER_ARTICLE_COPY',@LockMode=N'Exclusive',@LockOwner=N'Transaction',@LockTimeout=10000;
 IF @Lock<0 THROW 63004,N'Copie déjà en cours.',1;
 CREATE TABLE #Clients(code nvarchar(40) COLLATE DATABASE_DEFAULT PRIMARY KEY);
 INSERT #Clients SELECT code FROM @Clients;
 DECLARE @Table sysname,@Key sysname,@Cols nvarchar(max),@SelectCols nvarchar(max),@Query nvarchar(max),@Inserted int;
 DECLARE TablesToCopy CURSOR LOCAL FAST_FORWARD FOR SELECT T,K FROM (VALUES(1,N'ITMMASTER',N'ITMREF_0'),(2,N'ITMFACILIT',N'ITMREF_0')) V(N,T,K) ORDER BY N;
 OPEN TablesToCopy;FETCH NEXT FROM TablesToCopy INTO @Table,@Key;
 WHILE @@FETCH_STATUS=0
 BEGIN
  IF EXISTS(SELECT 1 FROM sys.columns T WHERE T.object_id=OBJECT_ID(N'TEST.'+@Table) AND T.is_identity=0 AND T.is_computed=0 AND T.system_type_id<>189 AND NOT EXISTS(
    SELECT 1 FROM sys.columns S WHERE S.object_id=OBJECT_ID(N'OB.'+@Table) AND S.name=T.name AND S.system_type_id=T.system_type_id AND (S.max_length=T.max_length OR (@Table=N'ITMMASTER' AND T.name=N'XITMREF_0' AND T.system_type_id=231 AND S.max_length=80 AND T.max_length=60)) AND S.precision=T.precision AND S.scale=T.scale))
   THROW 63005,N'Schémas OB/TEST incompatibles : aucune copie.',1;
  SELECT @Cols=STRING_AGG(CONVERT(nvarchar(max),QUOTENAME(name)),N',') WITHIN GROUP(ORDER BY column_id),
   @SelectCols=STRING_AGG(CONVERT(nvarchar(max),N'S.'+QUOTENAME(name)),N',') WITHIN GROUP(ORDER BY column_id)
   FROM sys.columns WHERE object_id=OBJECT_ID(N'TEST.'+@Table) AND is_identity=0 AND is_computed=0 AND system_type_id<>189;
  SET @Query=N'INSERT TEST.'+QUOTENAME(@Table)+N' ('+@Cols+N') SELECT '+@SelectCols+N' FROM OB.'+QUOTENAME(@Table)+N' S JOIN #Clients C ON S.'+QUOTENAME(@Key)+N'=C.code WHERE '+CASE WHEN @Table=N'ITMFACILIT' THEN N'S.STOFCY_0=N''201'' AND ' ELSE N'' END+N'NOT EXISTS(SELECT 1 FROM TEST.'+QUOTENAME(@Table)+N' T WITH(UPDLOCK,HOLDLOCK) WHERE T.'+QUOTENAME(@Key)+N'=S.'+QUOTENAME(@Key)+
   CASE WHEN @Table=N'ITMFACILIT' THEN N' AND T.STOFCY_0=S.STOFCY_0' ELSE N'' END+N'); SET @Inserted=@@ROWCOUNT;';
  EXEC sys.sp_executesql @Query,N'@Inserted int OUTPUT',@Inserted OUTPUT;
  INSERT @CopyLog VALUES(@Table,@Inserted);
  FETCH NEXT FROM TablesToCopy INTO @Table,@Key;
 END
 CLOSE TablesToCopy;DEALLOCATE TablesToCopy;
 IF EXISTS(SELECT 1 FROM #Clients C WHERE NOT EXISTS(SELECT 1 FROM TEST.ITMMASTER T WHERE T.ITMREF_0=C.code)) THROW 63112,'Controle copie articles echoue.',1;
 IF @CommitCopy=1 COMMIT TRANSACTION;ELSE ROLLBACK TRANSACTION;
 SELECT table_name,inserted_rows,@CommitCopy AS committed FROM @CopyLog;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
