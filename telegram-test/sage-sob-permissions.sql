/* A executer par un administrateur dans SSMS.
   Utilisateur SQL repris du compte configure dans l'agent : agent_sage_x3.
   Ce fichier ne cree aucune commande et ne modifie aucun compte de l'agent.
   Etape actuelle : preparation / lecture uniquement.
   Ces GRANT ajoutent des droits ; ils ne retirent pas les droits deja presents.
*/
USE [x3v12];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DATABASE_PRINCIPAL_ID(N'agent_sage_x3') IS NULL
    THROW 62001, 'Utilisateur agent_sage_x3 absent de x3v12 : verifier le mappage du login.', 1;

BEGIN TRY
    BEGIN TRANSACTION;
    GRANT SELECT ON OBJECT::[TEST].[BPCUSTOMER] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[BPADDRESS] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[FACILITY] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[SALESREP] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[BPSUPPLIER] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[ITMBPS] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[ITMMASTER] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[ITMFACILIT] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[SORDER] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[SORDERP] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[SORDERQ] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[SVCRVAT] TO [agent_sage_x3];
    GRANT SELECT ON OBJECT::[TEST].[AVALNUM] TO [agent_sage_x3];
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

/* ETAPE FUTURE UNIQUEMENT : droits utilises par la branche INSERT de la requete jointe.
   Bloc volontairement commente : inutile pour preparer les commandes.
   Ne limite pas les INSERT aux commandes Telegram ni l'UPDATE a un seul compteur.

GRANT INSERT ON OBJECT::[TEST].[SORDER] TO [agent_sage_x3];
GRANT INSERT ON OBJECT::[TEST].[SORDERP] TO [agent_sage_x3];
GRANT INSERT ON OBJECT::[TEST].[SORDERQ] TO [agent_sage_x3];
GRANT INSERT ON OBJECT::[TEST].[SVCRVAT] TO [agent_sage_x3];
GRANT UPDATE ON OBJECT::[TEST].[AVALNUM] ([VALEUR_0]) TO [agent_sage_x3];
*/

-- Verification a executer avec la connexion de l'utilisateur cible :
-- SELECT * FROM sys.fn_my_permissions(N'TEST.BPCUSTOMER', N'OBJECT');
-- SELECT * FROM sys.fn_my_permissions(N'TEST.SORDER', N'OBJECT');
-- SELECT * FROM sys.fn_my_permissions(N'TEST.AVALNUM', N'OBJECT');
