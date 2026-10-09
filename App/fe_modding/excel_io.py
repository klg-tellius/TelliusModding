"""Dependency-free XLSX import/export for the FE8 editors."""
from __future__ import annotations
import re, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from .formats import dispo, fe8data
MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main'; REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'; PKG='http://schemas.openxmlformats.org/package/2006/relationships'; CT='http://schemas.openxmlformats.org/package/2006/content-types'
ET.register_namespace('',MAIN); ET.register_namespace('r',REL)
_STAT_NAMES = tuple(name.lower() for name in fe8data.STAT_NAMES)
_ITEM_STAT_NAMES = tuple(name.lower() for name in fe8data.ITEM_STAT_BONUS_NAMES)


def _named_fields(prefix, names):
 return tuple(f'{prefix}_{name}' for name in names)


CHARACTER_FIELDS=('pid','mpid','fid','jid','sid0','sid1','sid2','aid_unpromoted','aid_promoted','level','build','weight','weapon_ranks','roster_order','biorhythm_pattern','start_transform_gauge','biorhythm_phase',*_named_fields('stat_bonus',_STAT_NAMES),*_named_fields('growth',_STAT_NAMES),*_named_fields('fixed_growth_start',_STAT_NAMES))
ITEM_FIELDS=('iid','miid','help_key','weapon_type','attack_type','rank',*(f'property{i}' for i in range(6)),*(f'category{i}' for i in range(2)),'effect','weapon_effect','cost','uses','might','hit','weight','crit','min_range','max_range','icon','weapon_exp',*_named_fields('stat_bonus',_ITEM_STAT_NAMES),*_named_fields('growth_bonus',_STAT_NAMES),'trail_color')
DISPO_FIELDS=[dispo.FIELD_NAMES.get(i,f'field{i}') for i in range(len(dispo.FIELD_LAYOUT))]
def _ref(r,c):
 o=''
 while c: c,rem=divmod(c-1,26); o=chr(65+rem)+o
 return f'{o}{r}'
def _flat(x,fields):
 out=[]
 for f in fields:
  if f.startswith('sid'): v=x.sids[int(f[3:])]
  elif f.startswith('stat_bonus_'): v=x.stat_bonus[(_ITEM_STAT_NAMES if len(x.stat_bonus) == len(_ITEM_STAT_NAMES) else _STAT_NAMES).index(f[11:])]
  elif f.startswith('fixed_growth_start_'): v=x.fixed_growth_start[_STAT_NAMES.index(f[19:])]
  elif f.startswith('growth_bonus_'): v=x.growth_bonus[_STAT_NAMES.index(f[13:])]
  elif f.startswith('growth_'): v=x.growth[_STAT_NAMES.index(f[7:])]
  elif f.startswith('property'): v=x.properties[int(f[8:])]
  elif f.startswith('category'): v=x.categories[int(f[8:])]
  else: v=getattr(x,f)
  out.append(v)
 return out


def _column(cols, field):
 """Find a current named header, while accepting the old indexed header."""
 if field in cols:
  return cols[field]
 for prefix, names in (('stat_bonus_', _ITEM_STAT_NAMES), ('stat_bonus_', _STAT_NAMES),
                       ('growth_bonus_', _STAT_NAMES), ('growth_', _STAT_NAMES),
                       ('fixed_growth_start_', _STAT_NAMES)):
  if field.startswith(prefix) and field[len(prefix):] in names:
   legacy = prefix[:-1] + str(names.index(field[len(prefix):]))
   if legacy in cols:
    return cols[legacy]
 return None


def _storage_field(field):
 for prefix, names in (('stat_bonus_', _ITEM_STAT_NAMES), ('stat_bonus_', _STAT_NAMES),
                       ('growth_bonus_', _STAT_NAMES), ('growth_', _STAT_NAMES),
                       ('fixed_growth_start_', _STAT_NAMES)):
  if field.startswith(prefix) and field[len(prefix):] in names:
   return prefix[:-1] + str(names.index(field[len(prefix):]))
 return field


def _cell(ref,v):
 c=ET.Element(f'{{{MAIN}}}c',{'r':ref})
 if v in (None,''): return c
 if isinstance(v,(int,float)) and not isinstance(v,bool): ET.SubElement(c,f'{{{MAIN}}}v').text=str(v)
 else:
  c.set('t','inlineStr'); ET.SubElement(ET.SubElement(c,f'{{{MAIN}}}is'),f'{{{MAIN}}}t').text=str(v)
 return c
def _sheet(rows):
 root=ET.Element(f'{{{MAIN}}}worksheet'); data=ET.SubElement(root,f'{{{MAIN}}}sheetData')
 for r,vals in enumerate(rows,1):
  row=ET.SubElement(data,f'{{{MAIN}}}row',{'r':str(r)})
  for c,v in enumerate(vals,1): row.append(_cell(_ref(r,c),v))
 return ET.tostring(root,encoding='utf-8',xml_declaration=True)
def write_workbook(path,sheets):
 names=list(sheets); wb=ET.Element(f'{{{MAIN}}}workbook'); sn=ET.SubElement(wb,f'{{{MAIN}}}sheets'); rels=ET.Element(f'{{{PKG}}}Relationships'); content=ET.Element(f'{{{CT}}}Types')
 ET.SubElement(content,f'{{{CT}}}Default',{'Extension':'rels','ContentType':'application/vnd.openxmlformats-package.relationships+xml'}); ET.SubElement(content,f'{{{CT}}}Default',{'Extension':'xml','ContentType':'application/xml'}); ET.SubElement(content,f'{{{CT}}}Override',{'PartName':'/xl/workbook.xml','ContentType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'})
 for i,name in enumerate(names,1):
  ET.SubElement(sn,f'{{{MAIN}}}sheet',{'name':name,'sheetId':str(i),f'{{{REL}}}id':f'rId{i}'}); ET.SubElement(rels,f'{{{PKG}}}Relationship',{'Id':f'rId{i}','Type':'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet','Target':f'worksheets/sheet{i}.xml'}); ET.SubElement(content,f'{{{CT}}}Override',{'PartName':f'/xl/worksheets/sheet{i}.xml','ContentType':'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
 with zipfile.ZipFile(Path(path),'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml',ET.tostring(content,encoding='utf-8',xml_declaration=True)); z.writestr('_rels/.rels',b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'); z.writestr('xl/workbook.xml',ET.tostring(wb,encoding='utf-8',xml_declaration=True)); z.writestr('xl/_rels/workbook.xml.rels',ET.tostring(rels,encoding='utf-8',xml_declaration=True))
  for i,rows in enumerate(sheets.values(),1): z.writestr(f'xl/worksheets/sheet{i}.xml',_sheet(rows))
def _col(ref):
 n=0
 for ch in re.match(r'[A-Z]+',ref.upper()).group(0): n=n*26+ord(ch)-64
 return n-1
def read_workbook(path):
 with zipfile.ZipFile(Path(path)) as z:
  wb=ET.fromstring(z.read('xl/workbook.xml')); rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels')); targets={r.attrib['Id']:r.attrib['Target'] for r in rels}; result={}
  for sheet in wb.find(f'{{{MAIN}}}sheets'):
   root=ET.fromstring(z.read('xl/'+targets[sheet.attrib[f'{{{REL}}}id']])); rows=[]
   for row in root.findall(f'.//{{{MAIN}}}row'):
    vals=[]
    for cell in row.findall(f'{{{MAIN}}}c'):
     i=_col(cell.attrib['r'])
     while len(vals)<=i: vals.append(None)
     if cell.attrib.get('t')=='inlineStr': n=cell.find(f'{{{MAIN}}}is/{{{MAIN}}}t'); v=n.text if n is not None else ''
     else:
      n=cell.find(f'{{{MAIN}}}v'); v=n.text if n is not None else None
      if v is not None:
       try: v=int(v) if re.fullmatch(r'-?\d+',v) else float(v)
       except ValueError: pass
     vals[i]=v
    rows.append(vals)
   result[sheet.attrib['name']]=rows
  return result
def export_fe8(path,data,docs=None,only=None):
 f=fe8data.read_fe8data(data) if data else None; sheets={}
 if f:
  if only in (None,'Characters'):
   sheets['Characters']=[['index',*CHARACTER_FIELDS]]+[[r.index,*_flat(r,CHARACTER_FIELDS)] for r in f.characters]
  if only in (None,'Items'):
   sheets['Items']=[['index',*ITEM_FIELDS]]+[[r.index,*_flat(r,ITEM_FIELDS)] for r in f.items]
 if docs:
  headers=['section','unit_index','linked_label',*DISPO_FIELDS]
  for name,doc in docs.items():
   rows=[headers]
   for s in doc.sections:
    if s.is_link: rows.append([s.name,'',s.header,*(['']*len(DISPO_FIELDS))])
    else:
     for i,u in enumerate(s.units): rows.append([s.name,i,'',*u])
   sheets['Dispo '+name.removeprefix('dispos_').removesuffix('.bin')]=rows
 write_workbook(path,sheets)
def _num(v,field):
 if v in (None,''): return None
 try: return int(v)
 except (TypeError,ValueError): raise ValueError(f'{field} must be a whole number') from None
def import_fe8(path,data,docs=None,only=None):
 sheets=read_workbook(path); parsed=fe8data.read_fe8data(data) if data else None; errors=[]; out=data
 for name,records,fields,patcher in ((('Characters',parsed.characters,CHARACTER_FIELDS,fe8data.patch_character_field),('Items',parsed.items,ITEM_FIELDS,fe8data.patch_item_field)) if parsed else ()):
  if only is not None and name != only:
   continue
  rows=sheets.get(name)
  if not rows: continue
  cols={str(v).strip().casefold():i for i,v in enumerate(rows[0]) if v is not None}
  if 'index' not in cols: errors.append(f'{name}: missing index column'); continue
  for rn,row in enumerate(rows[1:],2):
   if not any(v not in (None,'') for v in row): continue
   try:
    index=_num(row[cols['index']] if cols['index']<len(row) else None,'index'); record=next(r for r in records if r.index==index)
    for field in fields:
     col=_column(cols,field)
     if col is None or col>=len(row) or row[col] in (None,''): continue
     v=row[col]
     if field.startswith(('level','build','weight','roster_order','biorhythm_pattern','start_transform','stat_bonus','growth','fixed_growth','cost','uses','might','hit','crit','min_range','max_range','icon','weapon_exp','trail_color')): v=_num(v,field)
     elif field in ('pid','iid'): v=str(v).strip()
     elif field.startswith(('property','category')): v=str(v).strip()
     else: v=str(v).strip()
     if patcher is fe8data.patch_item_field and field.startswith(('property','category')): continue
     out=patcher(out,index,_storage_field(field),v)
    if patcher is fe8data.patch_item_field:
     for aggregate,prefix,count in (('properties','property',6),('categories','category',2)):
      if any(f'{prefix}{i}' in cols for i in range(count)):
       vals=[str(row[cols[f'{prefix}{i}']]).strip() for i in range(count) if f'{prefix}{i}' in cols and cols[f'{prefix}{i}'] < len(row) and row[cols[f'{prefix}{i}']] not in ('',None)]
       out=patcher(out,index,aggregate,vals)
   except (StopIteration,ValueError,TypeError,IndexError,KeyError) as e: errors.append(f'{name} row {rn}: {e or "unknown index"}')
 if docs:
  for name,doc in docs.items():
   rows=sheets.get('Dispo '+name.removeprefix('dispos_').removesuffix('.bin')); cols={str(v).strip().casefold():i for i,v in enumerate(rows[0])} if rows else {}
   for rn,row in enumerate(rows[1:],2) if rows else []:
    try:
     s=doc.section(str(row[cols['section']])); i=row[cols['unit_index']] if cols['unit_index']<len(row) else ''
     if s is None: raise ValueError('unknown section')
     if i in ('',None):
      if row[cols['linked_label']] not in ('',None): s.header=str(row[cols['linked_label']])
     else:
      u=s.units[int(i)]
      for fi,field in enumerate(DISPO_FIELDS):
       if field in cols and cols[field]<len(row) and row[cols[field]] not in ('',None): u[fi]=str(row[cols[field]]) if fi in dispo.POINTER_FIELDS else _num(row[cols[field]],field)
    except (ValueError,TypeError,IndexError,KeyError) as e: errors.append(f'{name} row {rn}: {e}')
 return out,docs,errors
