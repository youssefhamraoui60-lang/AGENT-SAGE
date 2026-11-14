/* Prérequis d’écriture SOB dans OB production.
   À exécuter dans SSMS par un administrateur de x3v12.
   Aucun INSERT de commande, aucune modification de compteur exécutés ici.
   Le service SOB ne doit être basculé vers OB qu’après vérification des droits
   et du paramétrage de création OB. Ce fichier ne change pas sa cible TEST.
   Les droits portent sur les objets indiqués, sans filtre de lignes ; le
   contrôle société/site/client et l’anti-doublon restent applicatifs.
*/
USE [x3v12];
GO
SET XACT_ABORT ON;
IF DATABASE_PRINCIPAL_ID(N'agent_sage_x3') IS NULL
    THROW 62001, 'Utilisateur agent_sage_x3 absent de x3v12.', 1;
IF SCHEMA_ID(N'OB') IS NULL
    THROW 62002, 'Dossier OB absent de x3v12.', 1;
BEGIN TRY
    BEGIN TRANSACTION;
    GRANT INSERT ON OBJECT::[OB].[SORDER] TO [agent_sage_x3];
    GRANT INSERT ON OBJECT::[OB].[SORDERP] TO [agent_sage_x3];
    GRANT INSERT ON OBJECT::[OB].[SORDERQ] TO [agent_sage_x3];
    GRANT INSERT ON OBJECT::[OB].[SVCRVAT] TO [agent_sage_x3];
    GRANT UPDATE ON OBJECT::[OB].[AVALNUM] ([VALEUR_0]) TO [agent_sage_x3];
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
-- Vérifier les cinq droits sous l’identité réellement utilisée par le service.
EXECUTE AS USER = N'agent_sage_x3';
SELECT HAS_PERMS_BY_NAME(N'OB.SORDER',N'OBJECT',N'INSERT') AS SORDER_INSERT,
       HAS_PERMS_BY_NAME(N'OB.SORDERP',N'OBJECT',N'INSERT') AS SORDERP_INSERT,
       HAS_PERMS_BY_NAME(N'OB.SORDERQ',N'OBJECT',N'INSERT') AS SORDERQ_INSERT,
       HAS_PERMS_BY_NAME(N'OB.SVCRVAT',N'OBJECT',N'INSERT') AS SVCRVAT_INSERT,
       HAS_PERMS_BY_NAME(N'OB.AVALNUM',N'OBJECT',N'UPDATE',N'VALEUR_0',N'COLUMN') AS COUNTER_UPDATE;
REVERT;
GO
