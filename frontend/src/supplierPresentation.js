export function supplierConversationText(content){
 if(content.startsWith('Bonjour ! Décrivez les articles souhaités.'))return 'Bonjour ! Indiquez le nom et les informations du fournisseur à créer. Je préparerai sa fiche pour votre confirmation.';
 const match=content.match(/^Fournisseur (.+?) préparé par SQL dans TEST\./);
 if(match)return 'La fiche du fournisseur '+match[1]+' est prête. Vérifiez les informations du tableau, puis cliquez sur « Confirmer la création ».';
 if(content.startsWith('Interprétation du brouillon tiers relue'))return 'Les informations du fournisseur ont été relues.';
 if(content.startsWith('Requête SQL fournisseur préparée'))return 'La fiche est prête. Vérifiez ses informations avant de confirmer la création.';
 return content;
}
