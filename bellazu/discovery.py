"""Inventory merging and similar-home ranking, independent of paid APIs and UI."""
import re


def address_key(address):
    text=re.sub(r'\s+\d{5}(?:-\d{4})?\s*$','',str(address or '').lower())
    text=re.sub(r'\b(apartment|apt\.?|unit|suite)\s*#?\s*', '#',text)
    for old,new in [('street','st'),('avenue','ave'),('road','rd'),('drive','dr'),('court','ct'),('boulevard','blvd'),('lane','ln')]:
        text=re.sub(r'\b'+old+r'\b',new,text)
    return re.sub(r'[^a-z0-9#]+',' ',text).strip()


def merge_rows(*groups):
    out=[]; ids=set(); addresses=set()
    for group in groups:
        for row in group or []:
            pid=str(row.get('id') or '')
            address=address_key(row.get('address'))
            if (pid and pid in ids) or (address and address in addresses):
                continue
            if not pid and not address:
                continue
            out.append(row)
            if pid: ids.add(pid)
            if address: addresses.add(address)
    return out


def active(row):
    flags=set(row.get('flags') or [])
    status=str(row.get('status') or 'for_sale').lower()
    return not (row.get('pending') or flags.intersection({'is_pending','is_contingent'}) or status in {'sold','pending','contingent','off_market','for_rent'})


def kind(row):
    k=row.get('kind')
    return {'multi':'2fam','townhome':'condo'}.get(k,k)


def similar(subject, candidates, *, budget, min_beds=0, towns=None, limit=6):
    """Rank available homes within the active area's criteria; never relax its budget."""
    allowed={str(t).strip().casefold() for t in (towns or [subject.get('town')]) if t}
    subject_id=str(subject.get('id') or '')
    subject_address=address_key(subject.get('address'))
    scored=[]
    for row in merge_rows(candidates):
        if (subject_id and str(row.get('id') or '')==subject_id) or (subject_address and address_key(row.get('address'))==subject_address):
            continue
        if not active(row) or not row.get('price') or row['price']>budget or (row.get('beds') or 0)<min_beds:
            continue
        if not allowed or str(row.get('town') or '').strip().casefold() not in allowed:
            continue
        if kind(subject) and kind(row)!=kind(subject):
            continue
        price=float(subject.get('price') or row['price'])
        gap=abs(float(row['price'])-price)/max(price,1)
        beds=abs(float(row.get('beds') or 0)-float(subject.get('beds') or row.get('beds') or 0))
        sqft=abs(float(row.get('sqft') or 0)-float(subject.get('sqft') or row.get('sqft') or 0))/max(float(subject.get('sqft') or 1),1)
        scored.append((gap+beds*.2+min(sqft,2)*.15,row))
    scored.sort(key=lambda x:(x[0],x[1]['price'],str(x[1].get('id') or x[1].get('address'))))
    return [r for _,r in scored[:max(0,limit)]]
