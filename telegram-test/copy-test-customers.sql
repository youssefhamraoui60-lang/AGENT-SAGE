SET NOCOUNT ON;
SET XACT_ABORT ON;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
DECLARE @Clients table(code nvarchar(30) PRIMARY KEY);
INSERT @Clients SELECT DISTINCT value FROM OPENJSON(@ClientsJSON);
IF EXISTS(SELECT 1 FROM @Clients C WHERE NOT EXISTS(SELECT 1 FROM OB.BPCUSTOMER S WHERE S.BPCNUM_0=C.code))
 THROW 63001,N'Client source absent OB.',1;
IF EXISTS(SELECT 1 FROM @Clients C JOIN TEST.BPARTNER T ON T.BPRNUM_0=C.code JOIN OB.BPARTNER S ON S.BPRNUM_0=C.code WHERE T.BPRNAM_0<>S.BPRNAM_0)
 THROW 63002,N'Conflit identité tiers TEST existant : aucune modification permise.',1;
IF EXISTS(SELECT 1 FROM @Clients C JOIN OB.BPCUSTOMER S ON S.BPCNUM_0=C.code WHERE
 (S.BPCINV_0<>'' AND NOT EXISTS(SELECT 1 FROM TEST.BPCUSTOMER T WHERE T.BPCNUM_0=S.BPCINV_0) AND NOT EXISTS(SELECT 1 FROM @Clients X WHERE X.code=S.BPCINV_0)) OR
 (S.BPCPYR_0<>'' AND NOT EXISTS(SELECT 1 FROM TEST.BPCUSTOMER T WHERE T.BPCNUM_0=S.BPCPYR_0) AND NOT EXISTS(SELECT 1 FROM @Clients X WHERE X.code=S.BPCPYR_0)))
 THROW 63003,N'Factureur/payeur absent TEST et hors liste approuvée.',1;
DECLARE @CopyLog table(table_name sysname,inserted_rows int);
BEGIN TRY
 BEGIN TRANSACTION;
 DECLARE @Lock int;
 EXEC @Lock=sys.sp_getapplock @Resource=N'SOB_TEST_MASTER_CUSTOMER_COPY',@LockMode=N'Exclusive',@LockOwner=N'Transaction',@LockTimeout=10000;
 IF @Lock<0 THROW 63004,N'Copie déjà en cours.',1;
 CREATE TABLE #Clients(code nvarchar(30) COLLATE DATABASE_DEFAULT PRIMARY KEY);
 INSERT #Clients SELECT code FROM @Clients;
 DECLARE @Table sysname,@Key sysname,@Cols nvarchar(max),@SelectCols nvarchar(max),@Query nvarchar(max),@Inserted int;
 DECLARE TablesToCopy CURSOR LOCAL FAST_FORWARD FOR SELECT T,K FROM (VALUES(1,N'BPARTNER',N'BPRNUM_0'),(2,N'BPADDRESS',N'BPANUM_0'),(3,N'BPCUSTOMER',N'BPCNUM_0')) V(N,T,K) ORDER BY N;
 OPEN TablesToCopy;FETCH NEXT FROM TablesToCopy INTO @Table,@Key;
 WHILE @@FETCH_STATUS=0
 BEGIN
  IF EXISTS(SELECT 1 FROM sys.columns T WHERE T.object_id=OBJECT_ID(N'TEST.'+@Table) AND T.is_identity=0 AND T.is_computed=0 AND T.system_type_id<>189 AND NOT EXISTS(
    SELECT 1 FROM sys.columns S WHERE S.object_id=OBJECT_ID(N'OB.'+@Table) AND S.name=T.name AND S.system_type_id=T.system_type_id AND S.max_length=T.max_length AND S.precision=T.precision AND S.scale=T.scale))
   THROW 63005,N'Schémas OB/TEST incompatibles : aucune copie.',1;
  SELECT @Cols=STRING_AGG(CONVERT(nvarchar(max),QUOTENAME(name)),N',') WITHIN GROUP(ORDER BY column_id),
   @SelectCols=STRING_AGG(CONVERT(nvarchar(max),N'S.'+QUOTENAME(name)),N',') WITHIN GROUP(ORDER BY column_id)
   FROM sys.columns WHERE object_id=OBJECT_ID(N'TEST.'+@Table) AND is_identity=0 AND is_computed=0 AND system_type_id<>189;
  SET @Query=N'INSERT TEST.'+QUOTENAME(@Table)+N' ('+@Cols+N') SELECT '+@SelectCols+N' FROM OB.'+QUOTENAME(@Table)+N' S JOIN #Clients C ON S.'+QUOTENAME(@Key)+N'=C.code WHERE NOT EXISTS(SELECT 1 FROM TEST.'+QUOTENAME(@Table)+N' T WITH(UPDLOCK,HOLDLOCK) WHERE T.'+QUOTENAME(@Key)+N'=S.'+QUOTENAME(@Key)+
   CASE WHEN @Table=N'BPADDRESS' THEN N' AND T.BPATYP_0=S.BPATYP_0 AND T.BPAADD_0=S.BPAADD_0' ELSE N'' END+N'); SET @Inserted=@@ROWCOUNT;';
  EXEC sys.sp_executesql @Query,N'@Inserted int OUTPUT',@Inserted OUTPUT;
  INSERT @CopyLog VALUES(@Table,@Inserted);
  FETCH NEXT FROM TablesToCopy INTO @Table,@Key;
 END
 CLOSE TablesToCopy;DEALLOCATE TablesToCopy;
 IF EXISTS(SELECT 1 FROM #Clients C LEFT JOIN TEST.BPCUSTOMER T ON T.BPCNUM_0=C.code LEFT JOIN TEST.BPARTNER B ON B.BPRNUM_0=C.code WHERE T.BPCNUM_0 IS NULL OR B.BPRNUM_0 IS NULL)
  THROW 63006,N'Contrôle de copie client/tiers échoué.',1;
 IF @CommitCopy=1 COMMIT TRANSACTION;ELSE ROLLBACK TRANSACTION;
 SELECT table_name,inserted_rows,@CommitCopy AS committed FROM @CopyLog;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
