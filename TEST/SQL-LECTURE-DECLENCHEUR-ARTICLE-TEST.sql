-- Lecture uniquement, à exécuter par un administrateur autorisé.
-- Aucun GRANT, aucune modification de déclencheur ni de données.
USE [x3v12];
SELECT SCHEMA_NAME(tb.schema_id) AS dossier,tb.name AS table_article,
 tr.name AS declencheur,te.type_desc AS evenement,tr.is_disabled,
 OBJECTPROPERTY(tr.object_id,'IsEncrypted') AS definition_chiffree,
 OBJECT_DEFINITION(tr.object_id) AS definition
FROM sys.triggers tr
JOIN sys.tables tb ON tb.object_id=tr.parent_id
LEFT JOIN sys.trigger_events te ON te.object_id=tr.object_id
WHERE SCHEMA_NAME(tb.schema_id)='TEST' AND tb.name='ITMMASTER'
ORDER BY tr.name,te.type_desc;
