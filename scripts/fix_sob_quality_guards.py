from pathlib import Path
p=Path('telegram-test/prepare.py');s=p.read_text(encoding='utf-8')
s=s.replace("if compact in ('br7','brique7','briquerouge7')", "if compact in ('br7','brique7','brique07','briques07','briquerouge7')")
s=s.replace("(?:fer(?:abeton)?|acier)?hat?", "(?:fer(?:abeton)?|acier)?ha(?:diametre|diam|d|t)?")
s=s.replace("(?:rab|fer(?:abeton)?|acierabeton)(?:diametre|diam|d|ha)?", "(?:rab|fer(?:abeton)?|acier(?:abeton)?)(?:diametre|diam|d|ha)?")
s=s.replace("(?:fe500)?', compact)", "(?:fe500|mm)?', compact)")
s=s.replace("^(client|[éÉ]metteur|contact)", "^(client|nom du client|acheteur|donneur d'ordre|[éÉ]metteur|contact)") if False else s
# Keep receiver NOM fields excluded: only explicit client-side role labels expand.
s=s.replace("^(client|[eé]metteur|contact)", "^(client|nom du client|client final|acheteur|[eé]metteur|contact)")
s=s.replace("            if len(compatible)==1:\n                articles=compatible", "            if len(compatible)==1:\n                confirmed=choose_reference('article',line['article'],compatible)\n                if len(confirmed)==1: articles=confirmed")
needle="    if not draft['lines']:\n        missing_fields.append('articles et quantités')"
s=s.replace(needle,"    from source_article_safety import missing_explicit_articles\n    absent=missing_explicit_articles(last_user,resolved,canonical_article)\n    for code in absent:\n        missing_fields.append('article explicite source non repris : '+code)\n        missing.append('Le message demande explicitement '+code+' ; aucune substitution ni création avant vérification.')\n        total_known=False\n"+needle)
t=p.with_name(p.name+'.tmp');t.write_text(s,encoding='utf-8');t.replace(p)
p=Path('telegram-test/read_documents_layout.py');s=p.read_text(encoding='utf-8')
old="""    if len(re.sub(r'\\W','',retry['text']))>len(re.sub(r'\\W','',first['text'])):
        return {**retry,'method':'ocr_illumination_retry'}
    return first"""
new="""    best={**retry,'method':'ocr_illumination_retry'} if len(re.sub(r'\\W','',retry['text']))>len(re.sub(r'\\W','',first['text'])) else first
    if len(re.sub(r'\\W','',best['text']))<40:
        for angle in (90,270):
            try:rotated=ocr(ImageOps.exif_transpose(image).rotate(angle,expand=True))
            except (ValueError,subprocess.TimeoutExpired):continue
            if len(re.sub(r'\\W','',rotated['text']))>len(re.sub(r'\\W','',best['text'])):
                best={**rotated,'method':'ocr_rotation_'+str(angle)}
            if len(re.sub(r'\\W','',best['text']))>=40:break
    return best"""
assert old in s;s=s.replace(old,new)
t=p.with_name(p.name+'.tmp');t.write_text(s,encoding='utf-8');t.replace(p)
