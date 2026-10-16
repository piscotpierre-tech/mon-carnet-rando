"""Cross-check the departmental pedestrian catalogues against regional SIT IDs.

Public listings only, with factual fields, public GPX links and immutable source
identifiers. Other sports are excluded by each portal's pedestrian filter.
"""
import concurrent.futures
import gzip
import hashlib
import html
import importlib
import json
import math
from pathlib import Path
import re
import sys
import unicodedata
import urllib.parse

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
source=importlib.import_module('collect-normandie')
prepare=importlib.import_module('prepare-catalogue')


def plain(text):return html.unescape(re.sub('<[^>]*>',' ',text)).strip()


def parse_cards(text,domain,department):
    result=[]
    for match in re.finditer(r'<a\b(?=[^>]*\bdata-id="ITINOR)([^>]+)>(.*?)</a>',text,re.S):
        attrs,body=match.groups()
        official=source.attr(attrs,'href')
        if not official or not official.startswith(domain):continue
        title=re.search(r'<(?:span|p)[^>]*class="(?:title-card|card__title)"[^>]*>(.*?)</(?:span|p)>',body,re.S)
        town=re.search(r'<(?:span|p)[^>]*class="(?:location|card__location location)"[^>]*>(.*?)</(?:span|p)>',body,re.S)
        if not title:continue
        distance=re.search(r'(\d+(?:[.,]\d+)?)\s*km',plain(body))
        r={'sourceId':source.attr(attrs,'data-id'),'name':plain(title[1]),'town':plain(town[1]) if town else source.DEPARTMENTS[department],
           'department':department,'km':float(distance[1].replace(',','.')) if distance else None,'official':official,'gpxSource':None}
        lon,lat=source.attr(attrs,'data-lng'),source.attr(attrs,'data-lat')
        if lon and lat:r['officialLocation']=[float(lon),float(lat)]
        result.append(r)
    return result


def detail(r):
    r=dict(r)
    if r.get('gpxSource'):
        return prepare.validate(r)
    try:
        text=source.get(r['official']).replace('\\/','/')
        links=sorted(set(html.unescape(u) for u in re.findall(r'https?://[^\s"<>\\]+\.gpx(?:\?[^\s"<>\\]*)?',text,re.I)))
        if len(links)==1:r['gpxSource']=links[0]
        elif len(links)>1:r['issue']='Plusieurs GPX proposés : correspondance à vérifier.'
    except Exception as error:r['issue']=str(error)
    return prepare.validate(r)


def collect():
    regional=json.loads((ROOT/'catalogue/inventaire-regional.json').read_text())['records']
    regional_by_id={r['sourceId']:r for r in regional}
    prepared={r['sourceId']:r for path in (ROOT/'catalogue/snapshots').glob('*.json.gz') for r in json.loads(gzip.decompress(path.read_bytes()))}
    audit=[];all_records={};overrides={}
    # Calvados's public IRIS search uses the same SIT identifiers as the region.
    base='https://www.explore-calvados.com/sejour/activites/balades-et-randonnees/a-pied/'
    records=[]
    for page in [1,2]:
        data=urllib.parse.urlencode({'idPage':'5609','lang':'fr','langCode':'fr','request':base,'posts_per_page':'100','paged':str(page),'type':'pagination'}).encode()
        response=json.loads(source.get('https://www.explore-calvados.com/wp-json/wp-etourisme/query/search',data))
        original=response['templates']['offers']
        replaced=original.replace('https://www.explore-calvados.com/itineraire/','https://www.normandie-tourisme.fr/itineraire/')
        rows=source.parse_list(replaced)
        for row in rows:row['official']=row['official'].replace('https://www.normandie-tourisme.fr/','https://www.explore-calvados.com/')
        records.extend(rows)
    audit.append({'department':'14','source':base,'total':len(records),'announcedTotal':168,'collectedAll':len(records)==168,'sameSitId':sum(r['sourceId'] in regional_by_id for r in records)})
    for r in records:all_records[r['sourceId']]=r
    # Manche and Eure expose ordinary, paginated pedestrian listings.
    for department,base,query,size,total_regex in [
        ('50','https://www.attitude-manche.fr/randonner/itineraires/','pedestre=1663',18,r'sur\s+(\d+)\s+résultat'),
        ('27','https://www.eureka-attractivite.fr/itineraires-randonnees-eure/','randonnees-pedestres=897',12,r'pagination-results__total">\s*(\d+)\s+résultat'),
    ]:
        first=source.get(base+'?'+query)
        match=re.search(total_regex,first);assert match,f'No total for {department}'
        total=int(match[1]);pages=math.ceil(total/size)
        urls=[base+'?'+query]+[base+f'page/{i}/?'+query for i in range(2,pages+1)]
        records={}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for text in pool.map(source.get,urls):
                for r in parse_cards(text,urllib.parse.urlsplit(base).scheme+'://'+urllib.parse.urlsplit(base).netloc,department):records[r['sourceId']]=r
        # Some ordinary listings randomise each page independently. Revisit the
        # public pages with a harmless snapshot query until their total is met.
        for pass_no in range(1,7):
            if len(records)>=total:break
            refreshed=[u+f'&inventaire=20261016-{pass_no}' for u in urls]
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                for text in pool.map(source.get,refreshed):
                    current=re.search(total_regex,text)
                    assert current and int(current[1])==total,'The source total changed during collection'
                    for r in parse_cards(text,urllib.parse.urlsplit(base).scheme+'://'+urllib.parse.urlsplit(base).netloc,department):records[r['sourceId']]=r
        audit.append({'department':department,'source':base+'?'+query,'total':len(records),'announcedTotal':total,'collectedAll':len(records)==total,'sameSitId':sum(s in regional_by_id for s in records)})
        all_records.update(records)
        print(f"Département {department} : {len(records)}/{total} références",flush=True)
    # Geotrek supplies explicit practice IDs; 4 is labelled Pédestre by its homepage.
    api='https://admin-rando-orne.com/api/v2/trek/?format=json&page_size=1000'
    raw=source.get(api);data=json.loads(raw)
    assert data['next'] is None and data['count']==len(data['results'])
    geotrek=[]
    for t in data['results']:
        if t['practice']!=4 or not t['published'].get('fr'):continue
        name=t['name']['fr'];slug=t['gpx'].rsplit('/',1)[-1].removesuffix('.gpx')
        r={'sourceId':f"ORNE-GEOTREK-{t['id']}",'name':name,'town':t.get('departure_city') or 'Orne',
           'department':'61','km':round(t['length_2d']/1000,1),'official':f"https://randonnee-normandie.com/trek/{t['id']}-{slug}",
           'gpxSource':t['gpx'],'officialLocation':t['departure_geom'],
           'sourceDeparture':t['departure'].get('fr') or None,'sourceParking':t['parking_location'],
           'sourceDurationMinutes':round(t['duration']*60) if t['duration'] is not None else None,
           'sourceAscent':t['ascent'],'sourceDescent':abs(t['descent']) if t['descent'] is not None else None,
           'sourceApi':t['url'],'sourceApiSha256':hashlib.sha256(raw.encode()).hexdigest()}
        geotrek.append(r);all_records[r['sourceId']]=r
    audit.append({'department':'61','source':'https://randonnee-normandie.com/search?practices=4','api':api,'total':len(geotrek),'announcedTotal':len(geotrek),'collectedAll':True,'sameSitId':0,'note':'Identifiants Geotrek distincts : comparaison des géométries nécessaire.'})
    selected=[]
    for sid,r in all_records.items():
        old=prepared.get(sid)
        if sid not in regional_by_id or not old or old['status']!='trace-verifiee':selected.append(r)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i,r in enumerate(pool.map(detail,selected),1):
            results.append(r)
            if i%20==0:print(f"GPX départementaux {i}/{len(selected)}",flush=True)
    # Preserve the portal's explicit GPX for Geotrek when the page has no link.
    # detail() leaves an existing source intact, so the published link is checked.
    complement=[r for r in results if r['sourceId'] not in regional_by_id]
    overrides=[r for r in results if r['sourceId'] in regional_by_id and r['status']=='trace-verifiee']
    metadata=lambda r:{k:v for k,v in r.items() if k!='segments'}
    (ROOT/'catalogue/inventaire-complementaire.json').write_text(json.dumps({'checkedAt':source.DATE,'sources':audit,'records':[metadata(r) for r in complement],'overrides':[metadata(r) for r in overrides]},ensure_ascii=False,indent=2)+'\n')
    (ROOT/'catalogue/snapshots/complements.json.gz').write_bytes(gzip.compress(json.dumps(complement+overrides,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
    print(f"Compléments : {len(complement)} références supplémentaires et {len(overrides)} fichiers récupérés pour les fiches régionales",flush=True)


if __name__=='__main__':collect()
