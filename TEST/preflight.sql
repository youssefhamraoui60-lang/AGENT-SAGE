    IF DB_NAME() <> N'x3v12' OR @@TRANCOUNT <> 1
        THROW 50100, 'Base ou transaction inattendue.', 1;
    IF NOT EXISTS(SELECT 1 FROM OB.BPARTNER WHERE BPRNUM_0=@CodeModele AND CRY_0=@Pays)
        THROW 50113, 'Pays du modele different de la demande.', 1;
    IF @Statut<>N'' AND (NOT EXISTS(SELECT 1 FROM OB.BPARTNER WHERE BPRNUM_0=@CodeModele AND ENAFLG_0=TRY_CONVERT(int,@Statut))
        OR NOT EXISTS(SELECT 1 FROM OB.BPSUPPLIER WHERE BPSNUM_0=@CodeModele AND ENAFLG_0=TRY_CONVERT(int,@Statut)))
        THROW 50114, 'Statut du modele different de la demande.', 1;
    IF NULLIF(LTRIM(RTRIM(@Nom)), N'') IS NULL
       OR NULLIF(LTRIM(RTRIM(@NomCourt)), N'') IS NULL
        THROW 50101, 'Champs obligatoires manquants.', 1;

    -- Validate ALL tables before the first INSERT, including types and lengths.
    IF EXISTS (
        SELECT 1 FROM @Tables t
        WHERE OBJECT_ID(N'TEST.'+t.Nom,'U') IS NULL
           OR OBJECT_ID(N'OB.'+t.Nom,'U') IS NULL
    ) THROW 50102, 'Table source ou cible absente.', 1;
    IF EXISTS (
        SELECT 1 FROM @Tables t
        JOIN sys.columns c ON c.object_id=OBJECT_ID(N'TEST.'+t.Nom)
        LEFT JOIN sys.columns s ON s.object_id=OBJECT_ID(N'OB.'+t.Nom) AND s.name=c.name
        WHERE c.is_identity=0 AND c.is_computed=0 AND c.system_type_id<>189 AND c.name<>'ROWID'
        AND (s.name IS NULL OR s.user_type_id<>c.user_type_id OR s.max_length<>c.max_length
             OR s.precision<>c.precision OR s.scale<>c.scale OR s.is_nullable<>c.is_nullable
             OR ISNULL(s.collation_name,'')<>ISNULL(c.collation_name,''))
    ) THROW 50103, 'Types, tailles ou nullabilite OB/TEST incompatibles.', 1;
    IF EXISTS (
        SELECT 1 FROM @Tables t JOIN sys.columns c ON c.object_id=OBJECT_ID(N'TEST.'+t.Nom)
        WHERE c.name='ROWID' AND c.is_identity=0 AND c.is_computed=0 AND c.default_object_id=0
    ) THROW 50104, 'ROWID non automatique.', 1;
    IF EXISTS(SELECT 1 FROM sys.check_constraints k JOIN @Tables t
        ON k.parent_object_id=OBJECT_ID(N'TEST.'+t.Nom)
        WHERE k.is_disabled=1 OR k.is_not_trusted=1)
       OR EXISTS(SELECT 1 FROM sys.foreign_keys k JOIN @Tables t
        ON k.parent_object_id=OBJECT_ID(N'TEST.'+t.Nom)
        WHERE k.is_disabled=1 OR k.is_not_trusted=1)
        THROW 50111, 'Contraintes TEST desactivees ou non fiables.', 1;

    DECLARE @Fields TABLE (Tab sysname, Col sysname, Val nvarchar(4000));
    INSERT @Fields VALUES
    ('BPARTNER','BPRNUM_0',N'F2147483647'),
    ('BPSUPPLIER','BPSNUM_0',N'F2147483647'),
    ('BPADDRESS','BPANUM_0',N'F2147483647'),
    ('BPARTNER','BPRNAM_0',@Nom),('BPARTNER','BPRSHO_0',@NomCourt),
    ('BPARTNER','XICE_0',@ICE),('BPARTNER','XIF_0',@IF),('BPARTNER','XRC_0',@RC),
    ('BPARTNER','XDATREG_0',CONVERT(nvarchar(30),@DateRegularite,126)),
    ('BPSUPPLIER','BPSNAM_0',@Nom),('BPSUPPLIER','BPSSHO_0',@NomCourt),
    ('BPSUPPLIER','BSGCOD_0',@Categorie),('BPSUPPLIER','ACCCOD_0',@CodeComptable),
    ('BPSUPPLIER','VACBPR_0',@RegimeTaxe),('BPSUPPLIER','PTE_0',@Paiement),
    ('BPSUPPLIER','CUR_0',@Devise),('BPSUPPLIER','PURPRITYP_0',CONVERT(nvarchar(10),@TypeMontant)),
    ('BPADDRESS','BPAADDLIG_0',@Adresse),('BPADDRESS','CTY_0',@Ville),
    ('BPADDRESS','TEL_0',@Telephone),('BPADDRESS','FAX_0',@Fax);
    IF EXISTS (
        SELECT 1 FROM @Fields f LEFT JOIN sys.columns c
          ON c.object_id=OBJECT_ID(N'TEST.'+f.Tab) AND c.name=f.Col
        WHERE c.name IS NULL OR c.is_computed=1 OR c.is_identity=1
          OR (c.max_length<>-1 AND c.system_type_id IN (167,175,231,239)
              AND CASE WHEN c.system_type_id IN (231,239) THEN DATALENGTH(f.Val)
                       ELSE DATALENGTH(CONVERT(varchar(4000),f.Val)) END > c.max_length)
    ) THROW 50105, 'Champ absent, non modifiable ou valeur trop longue.', 1;
    IF NOT EXISTS(SELECT 1 FROM TEST.TABPAYTERM WHERE PTE_0=@Paiement)
       OR NOT EXISTS(SELECT 1 FROM TEST.BPSCATEG WHERE BSGCOD_0=@Categorie)
       OR NOT EXISTS(SELECT 1 FROM TEST.TABCUR WHERE CUR_0=@Devise)
       OR NOT EXISTS(SELECT 1 FROM TEST.GACCCODE WHERE ACCCOD_0=@CodeComptable AND TYP_0=3)
       OR NOT EXISTS(SELECT 1 FROM TEST.TABVACBPR WHERE VACBPR_0=@RegimeTaxe AND ENAFLG_0=2)
       OR NOT EXISTS(SELECT 1 FROM TEST.TABCOUNTRY WHERE CRY_0=@Pays)
        THROW 50106, 'Paiement, categorie, devise ou code comptable absent de TEST.', 1;
    -- The local dictionary must explicitly associate the requested amount label.
    IF NOT EXISTS (
        SELECT 1 FROM TEST.ATABZON z JOIN TEST.APLSTD a ON a.LANCHP_0=z.NOLIB_0
        WHERE z.CODFIC_0='BPSUPPLIER' AND z.CODZONE_0='PURPRITYP'
          AND a.LANNUM_0=@TypeMontant AND a.LAN_0='FRA'
          AND ((@TypeLibelle='TTC' AND (a.LANMES_0 LIKE '%TTC%' OR a.LANMES_0 LIKE '%Toutes taxes%'))
            OR (@TypeLibelle='HT' AND (a.LANMES_0 LIKE '%HT%' OR a.LANMES_0 LIKE '%Hors taxe%')))
    ) THROW 50107, 'Correspondance HT/TTC non prouvee par le dictionnaire TEST.', 1;
    -- Duplicates block preparation and execution, without any override.
    IF EXISTS(SELECT 1 FROM TEST.BPARTNER WITH(UPDLOCK,HOLDLOCK)
        WHERE ((@ICE<>N'' AND XICE_0=@ICE) OR (@IF<>N'' AND XIF_0=@IF)
            OR (@RC<>N'' AND XRC_0=@RC) OR BPRNAM_0=@Nom))
        THROW 50109, 'Informations deja utilisees par un autre fournisseur.', 1;
    IF NOT EXISTS(SELECT 1 FROM OB.BPADDRESS a JOIN OB.BPSUPPLIER s
        ON s.BPSNUM_0=a.BPANUM_0 AND s.BPAADD_0=a.BPAADD_0
        JOIN OB.BPARTNER p ON p.BPRNUM_0=s.BPSNUM_0 AND p.BPAADD_0=a.BPAADD_0
        WHERE s.BPSNUM_0=@CodeModele AND a.BPATYP_0=1)
        THROW 50110, 'Adresse et type du modele incoherents.', 1;
