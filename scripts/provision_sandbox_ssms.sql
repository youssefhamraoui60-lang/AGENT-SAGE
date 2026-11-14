USE [master];
GO
IF DB_ID(N'AGENT_SAGE_X3_SANDBOX') IS NULL
    EXEC(N'CREATE DATABASE [AGENT_SAGE_X3_SANDBOX]');
GO
USE [AGENT_SAGE_X3_SANDBOX];
GO
IF SUSER_ID(N'agent_sage_x3') IS NULL
    THROW 51000, 'Login agent_sage_x3 absent : aucune creation de login automatique.', 1;
IF USER_ID(N'agent_sage_x3') IS NULL
    CREATE USER [agent_sage_x3] FOR LOGIN [agent_sage_x3];
IF SCHEMA_ID(N'simulation') IS NULL
    EXEC(N'CREATE SCHEMA [simulation] AUTHORIZATION [dbo]');
GRANT CONNECT TO [agent_sage_x3];
GRANT CREATE TABLE TO [agent_sage_x3];
GRANT ALTER, SELECT, INSERT, REFERENCES
    ON SCHEMA::[simulation] TO [agent_sage_x3];
GO
SELECT DB_NAME() AS sandbox, name AS utilisateur
FROM sys.database_principals WHERE name=N'agent_sage_x3';
