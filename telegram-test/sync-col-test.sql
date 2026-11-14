/* Explicit user authorization, 2026-11-09: align COL business data with OB.
   Only TEST is written. Preserve existing TEST row identities/AUUID.
   No stock, order, accounting or counter data is copied. */
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF NOT EXISTS(SELECT 1 FROM OB.ITMMASTER WHERE ITMREF_0=N'COL' AND ITMDES1_0 LIKE N'%TRADICEM%')
 THROW 63201,N'COL source TRADICEM absent.',1;
IF NOT EXISTS(SELECT 1 FROM TEST.ITMMASTER WHERE ITMREF_0=N'COL' AND ITMDES1_0 LIKE N'%TRADICEM%')
 THROW 63202,N'Identité COL TEST différente du produit approuvé.',1;
DECLARE @Table sysname,@Cols nvarchar(max),@Values nvarchar(max),@Set nvarchar(max),@Join nvarchar(max),@Filter nvarchar(max),@Sql nvarchar(max),@Lock int;
DECLARE @Changes TABLE(table_name sysname,updated_rows int,inserted_rows int);
DECLARE @Updated int,@Inserted int;
BEGIN TRY
 BEGIN TRANSACTION;
 EXEC @Lock=sys.sp_getapplock @Resource=N'SOB-sync-COL-TEST',@LockMode=N'Exclusive',@LockOwner=N'Transaction',@LockTimeout=10000;
 IF @Lock<0 THROW 63203,N'Verrou synchronisation indisponible.',1;
 SELECT N'BEFORE_ITMMASTER' AS stage,(SELECT * FROM TEST.ITMMASTER WHERE ITMREF_0=N'COL' FOR JSON PATH) AS snapshot;
 SELECT N'BEFORE_ITMSALES' AS stage,(SELECT * FROM TEST.ITMSALES WHERE ITMREF_0=N'COL' FOR JSON PATH) AS snapshot;
 SELECT N'BEFORE_ITMFACILIT' AS stage,(SELECT * FROM TEST.ITMFACILIT WHERE ITMREF_0=N'COL' AND STOFCY_0=N'201' FOR JSON PATH) AS snapshot;
 DECLARE Tables CURSOR LOCAL FAST_FORWARD FOR SELECT name FROM (VALUES(N'ITMMASTER'),(N'ITMSALES'),(N'ITMFACILIT')) T(name);
 OPEN Tables; FETCH NEXT FROM Tables INTO @Table;
 WHILE @@FETCH_STATUS=0
 BEGIN
  IF EXISTS(SELECT 1 FROM sys.columns T WHERE T.object_id=OBJECT_ID(N'TEST.'+@Table) AND T.is_identity=0 AND T.is_computed=0 AND T.system_type_id<>189 AND NOT EXISTS(SELECT 1 FROM sys.columns S WHERE S.object_id=OBJECT_ID(N'OB.'+@Table) AND S.name=T.name AND S.system_type_id=T.system_type_id AND (S.max_length=T.max_length OR (@Table=N'ITMMASTER' AND T.name=N'XITMREF_0' AND S.max_length=80 AND T.max_length=60 AND NOT EXISTS(SELECT 1 FROM OB.ITMMASTER WHERE ITMREF_0=N'COL' AND DATALENGTH(XITMREF_0)>60))) AND S.precision=T.precision AND S.scale=T.scale))
   THROW 63204,N'Schémas incompatibles.',1;
  SELECT @Cols=STRING_AGG(CONVERT(nvarchar(max),QUOTENAME(name)),N',') WITHIN GROUP(ORDER BY column_id),
         @Values=STRING_AGG(CONVERT(nvarchar(max),N'S.'+QUOTENAME(name)),N',') WITHIN GROUP(ORDER BY column_id)
   FROM sys.columns WHERE object_id=OBJECT_ID(N'TEST.'+@Table) AND is_identity=0 AND is_computed=0 AND system_type_id<>189;
  SELECT @Set=STRING_AGG(CONVERT(nvarchar(max),N'T.'+QUOTENAME(name)+N'=S.'+QUOTENAME(name)),N',') WITHIN GROUP(ORDER BY column_id)
   FROM sys.columns WHERE object_id=OBJECT_ID(N'TEST.'+@Table) AND is_identity=0 AND is_computed=0 AND system_type_id<>189 AND name NOT IN(N'ITMREF_0',N'STOFCY_0',N'AUUID_0');
  SET @Join=N'T.ITMREF_0=S.ITMREF_0'+CASE WHEN @Table=N'ITMFACILIT' THEN N' AND T.STOFCY_0=S.STOFCY_0' ELSE N'' END;
  SET @Filter=N'S.ITMREF_0=N''COL'''+CASE WHEN @Table=N'ITMFACILIT' THEN N' AND S.STOFCY_0=N''201''' ELSE N'' END;
  SET @Sql=N'UPDATE T SET '+@Set+N' FROM TEST.'+QUOTENAME(@Table)+N' T JOIN OB.'+QUOTENAME(@Table)+N' S ON '+@Join+N' WHERE '+@Filter+N'; SET @U=@@ROWCOUNT; INSERT TEST.'+QUOTENAME(@Table)+N' ('+@Cols+N') SELECT '+@Values+N' FROM OB.'+QUOTENAME(@Table)+N' S WHERE '+@Filter+N' AND NOT EXISTS(SELECT 1 FROM TEST.'+QUOTENAME(@Table)+N' T WITH(UPDLOCK,HOLDLOCK) WHERE '+@Join+N'); SET @I=@@ROWCOUNT;';
  EXEC sys.sp_executesql @Sql,N'@U int OUTPUT,@I int OUTPUT',@Updated OUTPUT,@Inserted OUTPUT;
  INSERT @Changes VALUES(@Table,@Updated,@Inserted);
  FETCH NEXT FROM Tables INTO @Table;
 END;
 CLOSE Tables; DEALLOCATE Tables;
 IF @CommitCopy=1 COMMIT TRANSACTION; ELSE ROLLBACK TRANSACTION;
 SELECT table_name,updated_rows,inserted_rows,@CommitCopy AS committed FROM @Changes;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
