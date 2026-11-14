import asyncio
from telegram_batch import OrderBatches,client_scoped_history


def test_bulk_named_code_inline_and_trailing_clients_stay_separate():
    async def run():
        got=[]
        async def process(key,messages):got.append([mid for mid,_ in messages])
        batches=OrderBatches(process,delay=.01)
        texts=[
            'Contact : Omri\nEl khayali sakan\n300 ciment45\n245 perfecto',
            'Contact : Omri\nChekabal bâtiment\n3 tonne6\n4 tonne8',
            'Contact : Abdelmajid\nHaouam Soufiane\n600 sacs cpj35',
            'Contact : Abdelmajid\nHicham qriaa\n24 unités collene55\n24 unités panoglue',
            'Contact : Reda\n12 tonnes ciment35\n500 kg fer12\nAérofrein construction',
            'Contact : Reda\n27t cpj35\nYzo groupe tamesna',
            'Contact : Wiam\nCmm rabat\n17 tonnes35\n10 tonnes45',
            'Contact : Wiam\nC05389\n300 sacs ciment45',
            'Contact : Othmane\nC05687\n30 Rlx Bitulife 4mm F/F',
            'Contact : Othmane\nMazagan hicham\n595 sac Cpj35Perfecto',
            'Contact : H\nCiment abda\n13400 brique7',
            "Contact : H\nAgri kamili\n2kg fil d'attache"]
        for i,t in enumerate(texts):batches.add(1,1,100+i,t)
        await asyncio.gather(*list(batches.tasks),return_exceptions=True)
        assert sorted(got)==[[100+i] for i in range(len(texts))]
        assert client_scoped_history([{'role':'user','content':texts[6]}],texts[7])==[]
        assert client_scoped_history([{'role':'user','content':texts[8]}],texts[9])==[]
        await batches.close()
    asyncio.run(run())


def test_trailing_client_reve_mat_is_not_attached_to_previous_cement():
    async def run():
        got=[]
        async def process(key,messages):got.append([mid for mid,_ in messages])
        b=OrderBatches(process,delay=.01)
        b.add(1,1,591,'Contact : Youssef\n60 sacs cpj45\nDHAIKA KHADIJA\nOmnia TRS')
        b.add(1,1,595,'Contact : Youssef\n2000 kg rab16\n1500 kg rab6\nSounassid\nREVE MAT\nDar Bouazza TRS300')
        b.add(1,1,596,'Contact : Youssef\n9.30 dh')
        await asyncio.gather(*list(b.tasks),return_exceptions=True)
        assert got==[[591],[595,596]]
        await b.close()
    asyncio.run(run())
