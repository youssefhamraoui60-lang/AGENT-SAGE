-- A PRESENTER A L'ADMINISTRATEUR. Ce fichier n'est jamais execute par l'agent.
-- Audit TEST du 04/11/2026 : UPDATE disponible sur les huit tables de fiches.
-- INSERT absent sur les deux objets ci-dessous : uniquement si creation d'unites autorisee.
USE [x3v12];
GO
GRANT INSERT ON OBJECT::[TEST].[TABUNIT] TO [agent_sage_x3];
GRANT INSERT ON OBJECT::[TEST].[TABCOEFF] TO [agent_sage_x3];
GO
-- Pour examiner le declencheur ITMMASTER_UPDTICK (definition non lisible actuellement).
-- Ce droit ne valide pas le declencheur : revue de sa definition et empreinte requises ensuite.
GRANT VIEW DEFINITION ON OBJECT::[TEST].[ITMMASTER] TO [agent_sage_x3];
GO
-- Lecture par l'administrateur, puis revue humaine. Ne jamais remplir la liste
-- modification-approved-triggers.json uniquement parce qu'un GRANT a reussi.
SELECT tr.name,OBJECT_DEFINITION(tr.object_id) AS definition,
 CONVERT(varchar(64),HASHBYTES('SHA2_256',OBJECT_DEFINITION(tr.object_id)),2) AS definition_sha256
FROM sys.triggers tr WHERE tr.parent_id=OBJECT_ID(N'TEST.ITMMASTER');
GO
-- Aucun droit DELETE, aucun droit sur un schema entier, aucun droit sur OB.
-- Aucune creation d'utilisateur, aucun REVOKE/DENY et aucun usage du compte sa.
