/* A executer dans SSMS par l'administrateur pour activer la creation SOB TEST.
   Aucun INSERT de commande execute par ce fichier.
   Les droits sont ceux utilises par la requete fournie par l'utilisateur.
   Le controle client/site/annee/validation est applique par l'application.
   Les GRANT ne limitent pas eux-memes les lignes accessibles au compte partage.
*/
USE [x3v12];
GO
SET XACT_ABORT ON;
IF DATABASE_PRINCIPAL_ID(N'agent_sage_x3') IS NULL
    THROW 62001, 'Utilisateur agent_sage_x3 absent de x3v12.', 1;
BEGIN TRY
    BEGIN TRANSACTION;
    GRANT INSERT ON OBJECT::[TEST].[SORDER] TO [agent_sage_x3];
    GRANT INSERT ON OBJECT::[TEST].[SORDERP] TO [agent_sage_x3];
    GRANT INSERT ON OBJECT::[TEST].[SORDERQ] TO [agent_sage_x3];
    GRANT INSERT ON OBJECT::[TEST].[SVCRVAT] TO [agent_sage_x3];
    GRANT UPDATE ON OBJECT::[TEST].[AVALNUM] ([VALEUR_0]) TO [agent_sage_x3];
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
