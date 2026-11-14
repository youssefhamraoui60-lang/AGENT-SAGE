USE [x3v12];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

---------------------------------------------------
-- 1. PARAMETRES
---------------------------------------------------

DECLARE @Unite NVARCHAR(3) = N'SC2';
DECLARE @Symbole NVARCHAR(5) = N'SC2';
DECLARE @Modele NVARCHAR(3) = N'SAC';
DECLARE @UniteStock NVARCHAR(3) = N'KG';

DECLARE @Decimales SMALLINT = 0;
DECLARE @TypeUnite TINYINT = 7;

DECLARE @Coefficient DECIMAL(18,7) = 25.0000000;
DECLARE @Inverse DECIMAL(18,7) = 0.0400000;

-- 1 = COMMIT
-- 0 = SIMULATION AVEC ROLLBACK
DECLARE @Appliquer BIT = 1;

BEGIN TRY

    BEGIN TRANSACTION;

    ---------------------------------------------------
    -- 2. VERIFIER LES UNITES
    ---------------------------------------------------

    IF EXISTS (
        SELECT 1
        FROM TEST.TABUNIT WITH (UPDLOCK, HOLDLOCK)
        WHERE UOM_0 = @Unite
    )
        THROW 50001,
            'Unite SC2 deja existante.',
            1;

    IF NOT EXISTS (
        SELECT 1
        FROM TEST.TABUNIT
        WHERE UOM_0 = @Modele
          AND UOMTYP_0 = 7
    )
        THROW 50002,
            'Modele SAC absent ou incorrect.',
            1;

    IF NOT EXISTS (
        SELECT 1
        FROM TEST.TABUNIT
        WHERE UOM_0 = @UniteStock
          AND UOMTYP_0 = 4
    )
        THROW 50003,
            'Unite KG absente ou incorrecte.',
            1;

    ---------------------------------------------------
    -- 3. VERIFIER LES DOUBLONS DE CONVERSION
    ---------------------------------------------------

    IF EXISTS (
        SELECT 1
        FROM TEST.TABCOEFF WITH (UPDLOCK, HOLDLOCK)
        WHERE
            (UOM1_0 = @Unite
             AND UOM2_0 = @UniteStock)
            OR
            (UOM1_0 = @UniteStock
             AND UOM2_0 = @Unite)
    )
        THROW 50004,
            'Une conversion existe deja.',
            1;

    ---------------------------------------------------
    -- 4. VERIFIER LES COEFFICIENTS
    ---------------------------------------------------

    IF @Coefficient <= 0
       OR @Inverse <= 0
       OR ABS(
           @Coefficient * @Inverse - 1
       ) > 0.0000001
        THROW 50005,
            'Coefficients de conversion incorrects.',
            1;

    ---------------------------------------------------
    -- 5. CREER LA NOUVELLE UNITE SC2
    ---------------------------------------------------

    INSERT INTO TEST.TABUNIT
    (
        UPDTICK_0,
        UOM_0,
        UOMDEC_0,
        UOMSYM_0,
        UOMTYP_0,
        INTSAU_0,
        CREUSR_0,
        CREDAT_0,
        UPDUSR_0,
        UPDDAT_0,
        CREDATTIM_0,
        UPDDATTIM_0,
        AUUID_0
    )
    SELECT
        1,
        @Unite,
        @Decimales,
        @Symbole,
        @TypeUnite,
        INTSAU_0,
        N'ADMIN',
        GETDATE(),
        N'ADMIN',
        GETDATE(),
        GETDATE(),
        GETDATE(),
        CONVERT(BINARY(16), NEWID())
    FROM TEST.TABUNIT
    WHERE UOM_0 = @Modele;

    IF @@ROWCOUNT <> 1
        THROW 50006,
            'Creation unite incorrecte.',
            1;

    ---------------------------------------------------
    -- 6. CONVERSION : SC2 VERS KG
    ---------------------------------------------------

    INSERT INTO TEST.TABCOEFF
    (
        UPDTICK_0,
        UOM1_0,
        UOM2_0,
        REV_0,
        COEUOM_0,
        CREUSR_0,
        CREDAT_0,
        UPDUSR_0,
        UPDDAT_0,
        CREDATTIM_0,
        UPDDATTIM_0,
        AUUID_0
    )
    VALUES
    (
        1,
        @Unite,
        @UniteStock,
        1,
        @Coefficient,
        N'ADMIN',
        GETDATE(),
        N'ADMIN',
        GETDATE(),
        GETDATE(),
        GETDATE(),
        CONVERT(BINARY(16), NEWID())
    );

    IF @@ROWCOUNT <> 1
        THROW 50007,
            'Creation coefficient SC2 vers KG incorrecte.',
            1;

    ---------------------------------------------------
    -- 7. CONVERSION : KG VERS SC2
    ---------------------------------------------------

    INSERT INTO TEST.TABCOEFF
    (
        UPDTICK_0,
        UOM1_0,
        UOM2_0,
        REV_0,
        COEUOM_0,
        CREUSR_0,
        CREDAT_0,
        UPDUSR_0,
        UPDDAT_0,
        CREDATTIM_0,
        UPDDATTIM_0,
        AUUID_0
    )
    VALUES
    (
        1,
        @UniteStock,
        @Unite,
        1,
        @Inverse,
        N'ADMIN',
        GETDATE(),
        N'ADMIN',
        GETDATE(),
        GETDATE(),
        GETDATE(),
        CONVERT(BINARY(16), NEWID())
    );

    IF @@ROWCOUNT <> 1
        THROW 50008,
            'Creation coefficient KG vers SC2 incorrecte.',
            1;

    ---------------------------------------------------
    -- 8. VERIFIER L'UNITE
    ---------------------------------------------------

    IF (
        SELECT COUNT(*)
        FROM TEST.TABUNIT
        WHERE UOM_0 = @Unite
          AND UOMSYM_0 = @Symbole
          AND UOMTYP_0 = @TypeUnite
          AND UOMDEC_0 = @Decimales
    ) <> 1
        THROW 50009,
            'Verification unite incorrecte.',
            1;

    ---------------------------------------------------
    -- 9. VERIFIER LES CONVERSIONS
    ---------------------------------------------------

    IF (
        SELECT COUNT(*)
        FROM TEST.TABCOEFF
        WHERE
           (
               UOM1_0 = @Unite
               AND UOM2_0 = @UniteStock
               AND COEUOM_0 = @Coefficient
           )
           OR
           (
               UOM1_0 = @UniteStock
               AND UOM2_0 = @Unite
               AND COEUOM_0 = @Inverse
           )
    ) <> 2
        THROW 50010,
            'Verification coefficients incorrecte.',
            1;

    ---------------------------------------------------
    -- 10. COMMIT OU ROLLBACK
    ---------------------------------------------------

    IF @Appliquer = 1
    BEGIN
        COMMIT TRANSACTION;

        SELECT
            'COMMIT - CREATION ENREGISTREE'
            AS RESULTAT;
    END
    ELSE
    BEGIN
        ROLLBACK TRANSACTION;

        SELECT
            'SIMULATION REUSSIE - ROLLBACK'
            AS RESULTAT;
    END;

    ---------------------------------------------------
    -- 11. AFFICHER LES DONNEES ENREGISTREES
    ---------------------------------------------------

    IF @Appliquer = 1
    BEGIN

        SELECT
            UOM_0 AS CODE_UNITE,
            UOMSYM_0 AS SYMBOLE,
            UOMDEC_0 AS DECIMALES,
            UOMTYP_0 AS TYPE_UNITE,
            INTSAU_0 AS CODE_UNITE_INTERNATIONALE
        FROM TEST.TABUNIT
        WHERE UOM_0 = @Unite;

        SELECT
            UOM1_0 AS UNITE_SOURCE,
            UOM2_0 AS UNITE_DESTINATION,
            COEUOM_0 AS COEFFICIENT,
            REV_0 AS REVERSIBLE
        FROM TEST.TABCOEFF
        WHERE UOM1_0 = @Unite
           OR UOM2_0 = @Unite
        ORDER BY UOM1_0, UOM2_0;

    END;

END TRY

BEGIN CATCH

    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    SELECT
        ERROR_NUMBER() AS NUMERO_ERREUR,
        ERROR_LINE() AS LIGNE_ERREUR,
        ERROR_MESSAGE() AS MESSAGE_ERREUR,
        'ROLLBACK' AS RESULTAT;

END CATCH;