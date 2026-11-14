-- Effective rights of the current SQL account. SELECT only; no GRANT, no DML.
SELECT name AS object_name,
 COALESCE(HAS_PERMS_BY_NAME(name,'OBJECT','SELECT'),0) AS can_select,
 COALESCE(HAS_PERMS_BY_NAME(name,'OBJECT','INSERT'),0) AS can_insert,
 requires_insert, requires_select,
 COALESCE(HAS_PERMS_BY_NAME(name,'OBJECT','EXECUTE'),0) AS can_execute,
 requires_execute
FROM (VALUES
 (N'TEST.BPARTNER',1,1,0),(N'TEST.BPSUPPLIER',1,1,0),(N'TEST.BPADDRESS',1,1,0),
 (N'OB.BPARTNER',0,1,0),(N'OB.BPSUPPLIER',0,1,0),(N'OB.BPADDRESS',0,1,0),
 (N'TEST.TABPAYTERM',0,1,0),(N'TEST.BPSCATEG',0,1,0),(N'TEST.TABCUR',0,1,0),
 (N'TEST.GACCCODE',0,1,0),(N'TEST.TABVACBPR',0,1,0),(N'TEST.TABCOUNTRY',0,1,0),
 (N'TEST.ATABZON',0,1,0),(N'TEST.APLSTD',0,1,0),
 (N'sys.columns',0,1,0),(N'sys.check_constraints',0,1,0),(N'sys.foreign_keys',0,1,0),
 (N'sys.sp_getapplock',0,0,1),(N'sys.sp_executesql',0,0,1)
) required(name,requires_insert,requires_select,requires_execute);
