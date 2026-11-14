-- Read-only diagnostic after a rejected preparation. No number is reserved.
WITH codes AS (
 SELECT BPRNUM_0 AS code FROM TEST.BPARTNER
 UNION ALL SELECT BPSNUM_0 FROM TEST.BPSUPPLIER
 UNION ALL SELECT BPANUM_0 FROM TEST.BPADDRESS
), numbers AS (
 SELECT TRY_CONVERT(int,SUBSTRING(code,2,30)) AS n FROM codes
 WHERE code LIKE 'F[0-9]%' AND SUBSTRING(code,2,30) NOT LIKE '%[^0-9]%'
), candidate AS (
 SELECT CASE WHEN MAX(n)=2147483647 THEN NULL
 ELSE CONCAT('F',CONVERT(bigint,ISNULL(MAX(n),0))+1) END AS proposed_code FROM numbers
)
SELECT c.proposed_code,p.BPRNUM_0 AS duplicate_code,p.BPRNAM_0 AS duplicate_name,
 p.XICE_0 AS existing_ice,p.XIF_0 AS existing_if,p.XRC_0 AS existing_rc,
 CASE WHEN EXISTS(SELECT 1 FROM TEST.BPSUPPLIER s WHERE s.BPSNUM_0=p.BPRNUM_0) THEN 1 ELSE 0 END AS supplier_exists,
 CASE WHEN @ICE<>N'' AND p.XICE_0=@ICE THEN 1 ELSE 0 END AS ice_match,
 CASE WHEN @IF<>N'' AND p.XIF_0=@IF THEN 1 ELSE 0 END AS fiscal_match,
 CASE WHEN @RC<>N'' AND p.XRC_0=@RC THEN 1 ELSE 0 END AS rc_match,
 CASE WHEN p.BPRNAM_0=@Nom THEN 1 ELSE 0 END AS name_match
FROM candidate c LEFT JOIN TEST.BPARTNER p
 ON (@ICE<>N'' AND p.XICE_0=@ICE) OR (@IF<>N'' AND p.XIF_0=@IF) OR (@RC<>N'' AND p.XRC_0=@RC) OR p.BPRNAM_0=@Nom
ORDER BY p.BPRNUM_0;
