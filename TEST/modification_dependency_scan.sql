-- Included only by the fixed worker. Caller declares @DependencyJson and @LockScan.
DECLARE @References table(tab sysname,col sysname,PRIMARY KEY(tab,col));
INSERT @References
SELECT DISTINCT t.name,c.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id
WHERE s.name='TEST' AND TYPE_NAME(c.system_type_id) IN ('nvarchar','nchar','varchar','char') AND (
 (@Resource='article' AND (c.name LIKE '%ITMREF%' OR EXISTS(SELECT 1 FROM TEST.ATABZON z WHERE z.CODFIC_0=t.name AND c.name LIKE REPLACE(z.CODZONE_0,'_','[_]')+'[_][0-9]%' AND (z.CODTYP_0='ITM' OR z.LIEN_0='ITMMASTER')))) OR
 (@Resource='supplier' AND (c.name LIKE '%BPSNUM%' OR c.name LIKE '%BPRNUM%' OR c.name LIKE '%BPANUM%' OR EXISTS(SELECT 1 FROM TEST.ATABZON z WHERE z.CODFIC_0=t.name AND c.name LIKE REPLACE(z.CODZONE_0,'_','[_]')+'[_][0-9]%' AND (z.CODTYP_0 IN ('BPS','BPR') OR z.LIEN_0 IN ('BPSUPPLIER','BPARTNER'))))));
DECLARE @DepRows table(tab sysname,has_matches bit,readable bit,columns_checked nvarchar(max),active bit,activity_rule nvarchar(200),evidence nvarchar(max));
DECLARE @DepTable sysname,@DepWhere nvarchar(max),@DepColumns nvarchar(max),@DepSql nvarchar(max),@DepFound bit,@DepActive bit,@DepRule nvarchar(200),@DepEvidence nvarchar(max),@DepStatus sysname,@DepClosed int,@DepValid nvarchar(max),@DepQtyExpr nvarchar(max);
DECLARE dep_scan CURSOR LOCAL FAST_FORWARD FOR SELECT tab,STRING_AGG(CONVERT(nvarchar(max),QUOTENAME(col)+'=@Lookup'),N' OR '),STRING_AGG(CONVERT(nvarchar(max),col),N',') WITHIN GROUP(ORDER BY col) FROM @References GROUP BY tab ORDER BY tab;
OPEN dep_scan;FETCH NEXT FROM dep_scan INTO @DepTable,@DepWhere,@DepColumns;
WHILE @@FETCH_STATUS=0 BEGIN
 SET @DepFound=NULL;SET @DepActive=NULL;SET @DepRule=NULL;SET @DepEvidence=NULL;
 BEGIN TRY
  IF HAS_PERMS_BY_NAME('TEST.'+@DepTable,'OBJECT','SELECT')<>1 THROW 50301,'Lecture dependance manquante.',1;
  SET @DepSql=N'SELECT @Found=CASE WHEN EXISTS(SELECT 1 FROM TEST.'+QUOTENAME(@DepTable)+CASE WHEN @LockScan=1 THEN N' WITH(HOLDLOCK)' ELSE N'' END+N' WHERE '+@DepWhere+N') THEN 1 ELSE 0 END;';
  EXEC sys.sp_executesql @DepSql,N'@Lookup nvarchar(128),@Found bit OUTPUT',@Code,@DepFound OUTPUT;
  SET @DepStatus=CASE @DepTable WHEN 'PORDER' THEN 'CLEFLG' WHEN 'PORDERQ' THEN 'LINCLEFLG' WHEN 'SORDER' THEN 'ORDSTA' WHEN 'SORDERQ' THEN 'SOQSTA' WHEN 'MFGHEAD' THEN 'MFGSTA' WHEN 'MFGITM' THEN 'MFGSTA' END;
  SET @DepClosed=NULL;SET @DepValid=NULL;
  IF @DepStatus IS NOT NULL AND COL_LENGTH('TEST.'+@DepTable,@DepStatus+'_0') IS NOT NULL BEGIN
   SELECT @DepClosed=MIN(l.LANNUM_0) FROM TEST.ATABZON z JOIN TEST.APLSTD l ON l.LANCHP_0=z.NOLIB_0 AND l.LAN_0='FRA' WHERE z.CODFIC_0=@DepTable AND z.CODZONE_0=@DepStatus AND z.NOLIB_0>0 AND l.LANNUM_0>0 AND LTRIM(RTRIM(l.LANMES_0)) COLLATE Latin1_General_CI_AI IN (N'Oui',N'Soldé',N'Soldée',N'Clos',N'Clôturé',N'Clôturée') HAVING COUNT(DISTINCT l.LANNUM_0)=1;
   SELECT @DepValid=STRING_AGG(CONVERT(nvarchar(max),l.LANNUM_0),',') FROM TEST.ATABZON z JOIN TEST.APLSTD l ON l.LANCHP_0=z.NOLIB_0 AND l.LAN_0='FRA' WHERE z.CODFIC_0=@DepTable AND z.CODZONE_0=@DepStatus AND z.NOLIB_0>0 AND l.LANNUM_0>0;
   IF @DepClosed IS NOT NULL AND @DepValid IS NOT NULL BEGIN
    SET @DepSql=N'SELECT @Active=CASE WHEN EXISTS(SELECT 1 FROM TEST.'+QUOTENAME(@DepTable)+CASE WHEN @LockScan=1 THEN N' WITH(HOLDLOCK)' ELSE N'' END+N' WHERE ('+@DepWhere+N') AND ('+QUOTENAME(@DepStatus+'_0')+N' IS NULL OR '+QUOTENAME(@DepStatus+'_0')+N' NOT IN ('+@DepValid+N'))) THEN NULL WHEN EXISTS(SELECT 1 FROM TEST.'+QUOTENAME(@DepTable)+CASE WHEN @LockScan=1 THEN N' WITH(HOLDLOCK)' ELSE N'' END+N' WHERE ('+@DepWhere+N') AND '+QUOTENAME(@DepStatus+'_0')+N'<>@Closed) THEN 1 ELSE 0 END;';
    EXEC sys.sp_executesql @DepSql,N'@Lookup nvarchar(128),@Closed int,@Active bit OUTPUT',@Code,@DepClosed,@DepActive OUTPUT;
    SET @DepRule=@DepTable+'.'+@DepStatus+'_0='+CONVERT(nvarchar(10),@DepClosed)+' (menu Sage verifie)';
   END;
  END;
  IF @DepTable IN ('STOCK','STOALL','ITMMVT') BEGIN
   SELECT @DepQtyExpr=STRING_AGG(CONVERT(nvarchar(max),N'SELECT N'''+c.name+N''' AS field,COALESCE(SUM(CONVERT(decimal(38,7),'+QUOTENAME(c.name)+N')),0) AS quantity,COALESCE(SUM(ABS(CONVERT(decimal(38,7),'+QUOTENAME(c.name)+N'))),0) AS absolute FROM TEST.'+QUOTENAME(@DepTable)+CASE WHEN @LockScan=1 THEN N' WITH(HOLDLOCK)' ELSE N'' END+N' WHERE '+@DepWhere),N' UNION ALL ') FROM sys.columns c WHERE c.object_id=OBJECT_ID('TEST.'+@DepTable) AND c.name IN ('QTYSTU_0','QTYSTUACT_0','SRGQTYSTU_0','CUMALLQTY_0','CUMALLQTA_0','CUMWIPQTY_0','PHYSTO_0','CTLSTO_0','REJSTO_0','PLFPHYSTO_0','PLFCTLSTO_0','PLFREJSTO_0','BPRPHYSTO_0','BPRCTLSTO_0','BPRREJSTO_0','SCOPHYSTO_0','SCOCTLSTO_0','SCOREJSTO_0','PHYALL_0','CTLALL_0','REJALL_0','GLOALL_0','SCOPHYALL_0','SCOCTLALL_0','SCOREJALL_0','TRFSTO_0','TRASTO_0','ORDSTO_0','SALSTO_0','WAISTO_0','SCCLNDSTO_0','SCCALL_0','CUNSTO_0');
   IF @DepQtyExpr IS NOT NULL BEGIN
    SET @DepSql=N'SELECT @Evidence=(SELECT * FROM ('+@DepQtyExpr+N') q ORDER BY field FOR JSON PATH);';
    EXEC sys.sp_executesql @DepSql,N'@Lookup nvarchar(128),@Evidence nvarchar(max) OUTPUT',@Code,@DepEvidence OUTPUT;
    SELECT @DepActive=CONVERT(bit,CASE WHEN EXISTS(SELECT 1 FROM OPENJSON(@DepEvidence) WITH(quantity decimal(38,7) '$.absolute') WHERE quantity<>0) THEN 1 ELSE 0 END);
    SET @DepRule='Quantites physiques, allocations et encours controles sans compensation des signes';
   END;
  END;
  INSERT @DepRows VALUES(@DepTable,@DepFound,1,@DepColumns,@DepActive,@DepRule,@DepEvidence);
 END TRY BEGIN CATCH INSERT @DepRows VALUES(@DepTable,NULL,0,@DepColumns,NULL,NULL,NULL); END CATCH;
 FETCH NEXT FROM dep_scan INTO @DepTable,@DepWhere,@DepColumns;
END;CLOSE dep_scan;DEALLOCATE dep_scan;
SELECT @DependencyJson=(SELECT CAST(CASE WHEN EXISTS(SELECT 1 FROM @DepRows WHERE readable=0) OR NOT EXISTS(SELECT 1 FROM @DepRows) THEN 0 ELSE 1 END AS bit) AS complete,'TEST_schema_and_Sage_dictionary' AS coverage,
 JSON_QUERY((SELECT * FROM @DepRows ORDER BY tab FOR JSON PATH,INCLUDE_NULL_VALUES)) AS sources FOR JSON PATH,WITHOUT_ARRAY_WRAPPER);
