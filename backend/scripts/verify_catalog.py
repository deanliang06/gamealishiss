import io
import json
from pathlib import Path
from PIL import Image, ImageDraw
from backend.app.sprites import Renderer, legal_specs, example_spec

def main():
    renderer=Renderer()
    specs=list(legal_specs())
    images=[]
    for spec in legal_specs(include_expressions=True): renderer.render(spec)
    for spec in specs:
        _,data=renderer.render(spec)
        image=Image.open(io.BytesIO(data))
        assert image.size==(64,64) and image.mode=='RGBA'
        assert len({p[:3] for p in image.get_flattened_data() if p[3]})<=5
        assert renderer.render(spec)[1]==data
        images.append(image)
    root=Path('docs/sprites'); root.mkdir(parents=True,exist_ok=True)
    preview=example_spec('fox_large_round',ears='paired_tall_triangles',tail='single_fluffy_zigzag',limbs='short_paws')
    (root/'preview.png').write_bytes(renderer.render(preview)[1])
    # Split sheets so every silhouette can be inspected at a legible scale.
    for page in range((len(images)+47)//48):
        subset=images[page*48:(page+1)*48]
        sheet=Image.new('RGB',(8*272,6*346),'#eee7dc')
        draw=ImageDraw.Draw(sheet)
        for i,im in enumerate(subset):
            x,y=(i%8)*272,(i//8)*346
            scaled=im.resize((256,256),Image.Resampling.NEAREST)
            sheet.paste(scaled,(x+8,y),scaled)
            draw.text((x+8,y+256),f'{page*48+i}: '+specs[page*48+i].silhouette.head.split('_')[0],fill='#222222')
            sheet.paste(im,(x+8,y+278),im)
        sheet.save(root/f'catalog-{page+1}.png')
    sheet=Image.new('RGB',(3*256,3*280),'#eee7dc');draw=ImageDraw.Draw(sheet)
    for h,head in enumerate(['fox_large_round','cat_round','lizard_round']):
        for e,eyes in enumerate(['alert','gentle','fierce']):
            spec=example_spec(head,eyes=eyes)
            im=Image.open(io.BytesIO(renderer.render(spec)[1])).resize((256,256),Image.Resampling.NEAREST)
            sheet.paste(im,(h*256,e*280),im);draw.text((h*256+8,e*280+256),head+' / '+eyes,fill='#222222')
    sheet.save(root/'expressions.png')
    (root/'index.json').write_text(json.dumps([s.model_dump() for s in specs],indent=2)+'\n')
    print(f'PASS: {len(specs)} legal silhouettes / {len(specs)*3} expression assemblies, deterministic pixels, bounds, baseline, palette and visibility')

if __name__=='__main__': main()
