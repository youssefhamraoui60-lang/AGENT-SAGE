USE [x3v12];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

-------------------------------------------------------
-- SECTION 1 : PARAMETRES A MODIFIER
-- POUR CHAQUE NOUVEAU FOURNISSEUR
-------------------------------------------------------

DECLARE @Nom NVARCHAR(100) = N'Télfix';
DECLARE @NomCourt NVARCHAR(30) = N'TELFIX';

DECLARE @ICE NVARCHAR(15) = N'001850814901094';
DECLARE @IF NVARCHAR(30) = N'20734924';
DECLARE @RC NVARCHAR(30) = N'10903';

DECLARE @DateRegularite DATETIME = '20260227';

DECLARE @Adresse NVARCHAR(100) = N'AYNE HARODA CASABLANCA';
DECLARE @Ville NVARCHAR(50) = N'CASABLANCA';

DECLARE @Telephone NVARCHAR(30) = N'06965654689';
DECLARE @Fax NVARCHAR(30) = N'515767829872';

DECLARE @Paiement NVARCHAR(10) = N'EFF60';
DECLARE @Categorie NVARCHAR(10) = N'FR';
DECLARE @CodeComptable NVARCHAR(10) = N'STD';
DECLARE @RegimeTaxe NVARCHAR(10) = N'MAR';
DECLARE @Devise NVARCHAR(10) = N'MAD';

-- Valeur numerique TTC a confirmer dans TEST
DECLARE @TypeMontant INT = 2;

-------------------------------------------------------
-- SECTION 2 : CONFIGURATION TECHNIQUE
-------------------------------------------------------

DECLARE @CodeModele NVARCHAR(30) = N'F103';
DECLARE @NouveauCode NVARCHAR(30);
DECLARE @DernierNumero INT;

DECLARE @Table SYSNAME;
DECLARE @Cle SYSNAME;
DECLARE @Colonnes NVARCHAR(MAX);
DECLARE @Valeurs NVARCHAR(MAX);
DECLARE @SQL NVARCHAR(MAX);

DECLARE @Verrou INT;
DECLARE @Erreur NVARCHAR(2048);

DECLARE @Tables TABLE (
    Ordre INT,
    Nom SYSNAME,
    Cle SYSNAME
);

INSERT INTO @Tables VALUES
(1, 'BPARTNER', 'BPRNUM_0'),
(2, 'BPADDRESS', 'BPANUM_0'),
(3, 'BPSUPPLIER', 'BPSNUM_0');

-------------------------------------------------------
-- SECTION 3 : CREATION
-------------------------------------------------------

BEGIN TRY

    BEGIN TRANSACTION;

    ---------------------------------------------------
    -- VERIFIER LES DOSSIERS
    ---------------------------------------------------

    IF SCHEMA_ID('TEST') IS NULL
        THROW 50001, 'Schema TEST introuvable.', 1;

    IF SCHEMA_ID('OB') IS NULL
        THROW 50002, 'Schema OB introuvable.', 1;

    ---------------------------------------------------
    -- VERIFIER LE FOURNISSEUR MODELE
    ---------------------------------------------------

    IF NOT EXISTS (
        SELECT 1 FROM OB.BPARTNER
        WHERE BPRNUM_0 = @CodeModele
    )
        THROW 50003, 'Modele BPARTNER absent.', 1;

    IF NOT EXISTS (
        SELECT 1 FROM OB.BPSUPPLIER
        WHERE BPSNUM_0 = @CodeModele
    )
        THROW 50004, 'Modele BPSUPPLIER absent.', 1;

    IF (
        SELECT COUNT(*)
        FROM OB.BPADDRESS
        WHERE BPANUM_0 = @CodeModele
    ) <> 1
        THROW 50005, 'Adresse modele non unique.', 1;

    ---------------------------------------------------
    -- VERIFIER ICE
    ---------------------------------------------------

    IF LEN(@ICE) <> 15
       OR @ICE LIKE '%[^0-9]%'
        THROW 50006, 'ICE invalide : 15 chiffres requis.', 1;

    ---------------------------------------------------
    -- VERIFIER TYPE MONTANT
    ---------------------------------------------------

    IF @TypeMontant NOT IN (1, 2)
        THROW 50007, 'Type montant invalide.', 1;

    ---------------------------------------------------
    -- VERROUILLAGE DE LA NUMEROTATION
    ---------------------------------------------------

    EXEC @Verrou = sys.sp_getapplock
        @Resource = 'TEST_CREATION_FOURNISSEUR',
        @LockMode = 'Exclusive',
        @LockOwner = 'Transaction',
        @LockTimeout = 10000;

    IF @Verrou < 0
        THROW 50008, 'Verrouillage impossible.', 1;

    ---------------------------------------------------
    -- RECHERCHER LE PLUS GRAND CODE FOURNISSEUR
    ---------------------------------------------------

    SELECT @DernierNumero = MAX(NUMERO)
    FROM (
        SELECT TRY_CONVERT(
            INT, SUBSTRING(BPRNUM_0, 2, 30)
        ) AS NUMERO
        FROM TEST.BPARTNER WITH (TABLOCKX, HOLDLOCK)
        WHERE BPRNUM_0 LIKE 'F[0-9]%'
          AND SUBSTRING(BPRNUM_0, 2, 30)
              NOT LIKE '%[^0-9]%'

        UNION ALL

        SELECT TRY_CONVERT(
            INT, SUBSTRING(BPSNUM_0, 2, 30)
        )
        FROM TEST.BPSUPPLIER WITH (TABLOCKX, HOLDLOCK)
        WHERE BPSNUM_0 LIKE 'F[0-9]%'
          AND SUBSTRING(BPSNUM_0, 2, 30)
              NOT LIKE '%[^0-9]%'

        UNION ALL

        SELECT TRY_CONVERT(
            INT, SUBSTRING(BPANUM_0, 2, 30)
        )
        FROM TEST.BPADDRESS WITH (TABLOCKX, HOLDLOCK)
        WHERE BPANUM_0 LIKE 'F[0-9]%'
          AND SUBSTRING(BPANUM_0, 2, 30)
              NOT LIKE '%[^0-9]%'
    ) X;

    IF @DernierNumero = 2147483647
        THROW 50009, 'Limite numerotation atteinte.', 1;

    SET @NouveauCode = CONCAT(
        'F', ISNULL(@DernierNumero, 0) + 1
    );

    PRINT 'NOUVEAU CODE : ' + @NouveauCode;

    ---------------------------------------------------
    -- VERIFIER CODE INEXISTANT
    ---------------------------------------------------

    IF EXISTS (
        SELECT 1 FROM TEST.BPARTNER
        WHERE BPRNUM_0 = @NouveauCode
    )
    OR EXISTS (
        SELECT 1 FROM TEST.BPSUPPLIER
        WHERE BPSNUM_0 = @NouveauCode
    )
    OR EXISTS (
        SELECT 1 FROM TEST.BPADDRESS
        WHERE BPANUM_0 = @NouveauCode
    )
        THROW 50010, 'Code deja utilise.', 1;

    ---------------------------------------------------
    -- GENERER LES INSERTIONS POUR CHAQUE TABLE
    ---------------------------------------------------

    DECLARE CurTables CURSOR LOCAL FAST_FORWARD FOR
        SELECT Nom, Cle
        FROM @Tables
        ORDER BY Ordre;

    OPEN CurTables;

    FETCH NEXT FROM CurTables INTO @Table, @Cle;

    WHILE @@FETCH_STATUS = 0
    BEGIN

        SET @Colonnes = NULL;
        SET @Valeurs = NULL;

        ------------------------------------------------
        -- VERIFIER LA STRUCTURE DES TABLES
        ------------------------------------------------

        IF OBJECT_ID('OB.' + @Table, 'U') IS NULL
           OR OBJECT_ID('TEST.' + @Table, 'U') IS NULL
            THROW 50011, 'Table source ou cible absente.', 1;

        IF EXISTS (
            SELECT 1
            FROM sys.columns C
            WHERE C.object_id = OBJECT_ID('TEST.' + @Table)
              AND C.name = 'ROWID'
              AND C.is_identity = 0
              AND C.is_computed = 0
              AND C.default_object_id = 0
        )
            THROW 50012,
                'ROWID non automatique. Insertion bloquee.',
                1;

        IF EXISTS (
            SELECT 1
            FROM sys.columns C
            WHERE C.object_id = OBJECT_ID('TEST.' + @Table)
              AND C.is_identity = 0
              AND C.is_computed = 0
              AND C.system_type_id <> 189
              AND C.name <> 'ROWID'
              AND NOT EXISTS (
                  SELECT 1
                  FROM sys.columns S
                  WHERE S.object_id = OBJECT_ID('OB.' + @Table)
                    AND S.name = C.name
              )
        )
            THROW 50013,
                'Colonnes incompatibles entre OB et TEST.',
                1;

        ------------------------------------------------
        -- LISTE DE TOUTES LES COLONNES INSERTABLES
        ------------------------------------------------

        SELECT
            @Colonnes = STRING_AGG(
                CAST(QUOTENAME(C.name) AS NVARCHAR(MAX)),
                ','
            ) WITHIN GROUP (ORDER BY C.column_id),

            @Valeurs = STRING_AGG(
                CAST(
                    CASE
                        -- Identifiant
                        WHEN C.name = @Cle
                            THEN '@NouveauCode'

                        -- Noms
                        WHEN C.name IN ('BPRNAM_0','BPSNAM_0')
                            THEN '@Nom'

                        WHEN C.name = 'BPRNAM_1'
                            THEN 'N'''''

                        WHEN C.name IN ('BPRSHO_0','BPSSHO_0')
                            THEN '@NomCourt'

                        -- Informations fiscales
                        WHEN C.name = 'XICE_0'
                            THEN '@ICE'

                        WHEN C.name = 'XIF_0'
                            THEN '@IF'

                        WHEN C.name = 'XRC_0'
                            THEN '@RC'

                        WHEN C.name = 'XDATREG_0'
                            THEN '@DateRegularite'

                        -- Ne pas copier les autres
                        -- identifiants fiscaux de F103
                        WHEN @Table = 'BPARTNER'
                         AND C.name IN (
                            'VATNUM_0',
                            'CRN_0',
                            'REGNUM_0',
                            'VATNO_0',
                            'XCIN_0'
                        )
                            THEN 'N'''''

                        -- Parametres fournisseur
                        WHEN @Table = 'BPSUPPLIER'
                         AND C.name = 'BSGCOD_0'
                            THEN '@Categorie'

                        WHEN @Table = 'BPSUPPLIER'
                         AND C.name = 'ACCCOD_0'
                            THEN '@CodeComptable'

                        WHEN @Table = 'BPSUPPLIER'
                         AND C.name = 'VACBPR_0'
                            THEN '@RegimeTaxe'

                        WHEN @Table = 'BPSUPPLIER'
                         AND C.name = 'PTE_0'
                            THEN '@Paiement'

                        WHEN @Table = 'BPSUPPLIER'
                         AND C.name = 'CUR_0'
                            THEN '@Devise'

                        -- TYPE MONTANT TTC
                        WHEN @Table = 'BPSUPPLIER'
                         AND C.name = 'PURPRITYP_0'
                            THEN '@TypeMontant'

                        -- References internes
                        WHEN @Table = 'BPSUPPLIER'
                         AND C.name IN (
                            'BPRPAY_0',
                            'BPSINV_0',
                            'BPSGRU_0',
                            'BPSRSK_0'
                        )
                            THEN '@NouveauCode'

                        -- Adresse
                        WHEN @Table = 'BPADDRESS'
                         AND C.name = 'BPAADDLIG_0'
                            THEN '@Adresse'

                        WHEN @Table = 'BPADDRESS'
                         AND C.name = 'CTY_0'
                            THEN '@Ville'

                        WHEN @Table = 'BPADDRESS'
                         AND C.name = 'TEL_0'
                            THEN '@Telephone'

                        WHEN @Table = 'BPADDRESS'
                         AND C.name = 'FAX_0'
                            THEN '@Fax'

                        -- Identification technique
                        WHEN C.name = 'AUUID_0'
                            THEN 'CONVERT(binary(16),NEWID())'

                        WHEN C.name = 'UPDTICK_0'
                            THEN '1'

                        WHEN C.name IN ('CREUSR_0','UPDUSR_0')
                            THEN 'N''ADMIN'''

                        WHEN C.name IN ('CREDAT_0','UPDDAT_0')
                            THEN 'CONVERT(datetime,GETDATE())'

                        WHEN C.name IN (
                            'CREDATTIM_0',
                            'UPDDATTIM_0'
                        )
                            THEN 'GETDATE()'

                        -- Copier les autres parametres
                        ELSE 'SRC.' + QUOTENAME(C.name)

                    END AS NVARCHAR(MAX)
                ),
                ','
            ) WITHIN GROUP (ORDER BY C.column_id)

        FROM sys.columns C
        WHERE C.object_id = OBJECT_ID('TEST.' + @Table)
          AND C.is_identity = 0
          AND C.is_computed = 0
          AND C.system_type_id <> 189
          AND C.name <> 'ROWID';

        ------------------------------------------------
        -- EXECUTER INSERT
        ------------------------------------------------

        IF @Colonnes IS NULL OR @Valeurs IS NULL
            THROW 50014, 'Generation SQL impossible.', 1;

        SET @SQL = N'
            INSERT INTO TEST.' + QUOTENAME(@Table) + N'
            (' + @Colonnes + N')
            SELECT ' + @Valeurs + N'
            FROM OB.' + QUOTENAME(@Table) + N' SRC
            WHERE SRC.' + QUOTENAME(@Cle) + N' = @CodeModele;

            IF @@ROWCOUNT <> 1
                THROW 50015,
                    ''Insertion absente ou multiple.'', 1;
        ';

        EXEC sys.sp_executesql
            @SQL,
            N'
                @CodeModele NVARCHAR(30),
                @NouveauCode NVARCHAR(30),
                @Nom NVARCHAR(100),
                @NomCourt NVARCHAR(30),
                @ICE NVARCHAR(15),
                @IF NVARCHAR(30),
                @RC NVARCHAR(30),
                @DateRegularite DATETIME,
                @Adresse NVARCHAR(100),
                @Ville NVARCHAR(50),
                @Telephone NVARCHAR(30),
                @Fax NVARCHAR(30),
                @Paiement NVARCHAR(10),
                @Categorie NVARCHAR(10),
                @CodeComptable NVARCHAR(10),
                @RegimeTaxe NVARCHAR(10),
                @Devise NVARCHAR(10),
                @TypeMontant INT
            ',
            @CodeModele = @CodeModele,
            @NouveauCode = @NouveauCode,
            @Nom = @Nom,
            @NomCourt = @NomCourt,
            @ICE = @ICE,
            @IF = @IF,
            @RC = @RC,
            @DateRegularite = @DateRegularite,
            @Adresse = @Adresse,
            @Ville = @Ville,
            @Telephone = @Telephone,
            @Fax = @Fax,
            @Paiement = @Paiement,
            @Categorie = @Categorie,
            @CodeComptable = @CodeComptable,
            @RegimeTaxe = @RegimeTaxe,
            @Devise = @Devise,
            @TypeMontant = @TypeMontant;

        PRINT 'INSERT OK : ' + @Table;

        FETCH NEXT FROM CurTables INTO @Table, @Cle;

    END;

    CLOSE CurTables;
    DEALLOCATE CurTables;

    ---------------------------------------------------
    -- CONTROLE AVANT VALIDATION
    ---------------------------------------------------

    IF (
        SELECT COUNT(*)
        FROM TEST.BPARTNER
        WHERE BPRNUM_0 = @NouveauCode
    ) <> 1
        THROW 50016, 'Erreur BPARTNER.', 1;

    IF (
        SELECT COUNT(*)
        FROM TEST.BPSUPPLIER
        WHERE BPSNUM_0 = @NouveauCode
    ) <> 1
        THROW 50017, 'Erreur BPSUPPLIER.', 1;

    IF (
        SELECT COUNT(*)
        FROM TEST.BPADDRESS
        WHERE BPANUM_0 = @NouveauCode
    ) <> 1
        THROW 50018, 'Erreur BPADDRESS.', 1;

    ---------------------------------------------------
    -- VALIDATION SQL
    ---------------------------------------------------

    COMMIT TRANSACTION;

    ---------------------------------------------------
    -- RESULTAT COMPLET
    ---------------------------------------------------

    SELECT
        BPR.BPRNUM_0 AS CODE_FOURNISSEUR,
        BPR.BPRNAM_0 AS RAISON_SOCIALE,

        BPR.XICE_0 AS ICE,
        BPR.XIF_0 AS IF_FISCAL,
        BPR.XRC_0 AS RC,
        BPR.XDATREG_0 AS DATE_REGULARITE,

        BPS.BSGCOD_0 AS CATEGORIE,
        BPS.ACCCOD_0 AS CODE_COMPTABLE,
        BPS.PTE_0 AS CONDITION_PAIEMENT,
        BPS.VACBPR_0 AS REGIME_TAXE,
        BPS.CUR_0 AS DEVISE,
        BPS.PURPRITYP_0 AS TYPE_MONTANT,

        BPA.BPAADDLIG_0 AS ADRESSE,
        BPA.CTY_0 AS VILLE,
        BPA.TEL_0 AS TELEPHONE,
        BPA.FAX_0 AS FAX,

        'INSERTIONS SQL TERMINEES' AS RESULTAT

    FROM TEST.BPARTNER BPR

    JOIN TEST.BPSUPPLIER BPS
        ON BPS.BPSNUM_0 = BPR.BPRNUM_0

    LEFT JOIN TEST.BPADDRESS BPA
        ON BPA.BPANUM_0 = BPR.BPRNUM_0
       AND BPA.BPAADD_0 = BPS.BPAADD_0

    WHERE BPR.BPRNUM_0 = @NouveauCode;

END TRY

BEGIN CATCH

    IF CURSOR_STATUS('local','CurTables') >= 0
        CLOSE CurTables;

    IF CURSOR_STATUS('local','CurTables') >= -1
        DEALLOCATE CurTables;

    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    SELECT
        ERROR_NUMBER() AS NUMERO_ERREUR,
        ERROR_LINE() AS LIGNE_ERREUR,
        ERROR_MESSAGE() AS MESSAGE_ERREUR,
        'ROLLBACK' AS ETAT_TRANSACTION;

END CATCH;