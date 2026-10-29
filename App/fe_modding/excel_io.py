"""Dependency-free XLSX import/export for the FE8 editors."""
from __future__ import annotations
import re, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from .formats import dispo, fe8data, fe10growth
MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main'; REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'; PKG='http://schemas.openxmlformats.org/package/2006/relationships'; CT='http://schemas.openxmlformats.org/package/2006/content-types'
ET.register_namespace('',MAIN); ET.register_namespace('r',REL)
_STAT_NAMES = tuple(name.lower() for name in fe8data.STAT_NAMES)
_ITEM_STAT_NAMES = tuple(name.lower() for name in fe8data.ITEM_STAT_BONUS_NAMES)


def _named_fields(prefix, names):
 return tuple(f'{prefix}_{name}' for name in names)


CHARACTER_FIELDS=('pid','mpid','fid','jid','sid0','sid1','sid2','aid_unpromoted','aid_promoted','level','build','weight','weapon_ranks','roster_order','biorhythm_pattern','start_transform_gauge','biorhythm_phase',*_named_fields('stat_bonus',_STAT_NAMES),*_named_fields('growth',_STAT_NAMES),*_named_fields('fixed_growth_start',_STAT_NAMES))
ITEM_FIELDS=('iid','miid','help_key','weapon_type','attack_type','rank',*(f'property{i}' for i in range(6)),*(f'category{i}' for i in range(2)),'effect','weapon_effect','cost','uses','might','hit','weight','crit','min_range','max_range','icon','weapon_exp',*_named_fields('stat_bonus',_ITEM_STAT_NAMES),*_named_fields('growth_bonus',_STAT_NAMES),'trail_color')
TERRAIN_FIELDS=('name','name_key','avoid','defense','resistance','alt_avoid','alt_defense','alt_resistance','heal','object_tile',*(f'move_cost_{i}' for i in range(len(fe8data.MOVEMENT_TYPE_NAMES))))
FE8_SHEETS=('Characters','Items','Terrain')
DISPO_FIELDS=[dispo.FIELD_NAMES.get(i,f'field{i}') for i in range(len(dispo.FIELD_LAYOUT))]
#: The unit flags (field 38) and item flags (40-47) as one yes/no column per bit.
_UNIT_FLAG_COLUMNS=(('autolevel',dispo.FLAG_AUTOLEVEL),('hold_position',dispo.FLAG_HOLD_POSITION),
 ('group_commander',dispo.FLAG_COMMANDER),('create_if_not_recruited',dispo.FLAG_SPAWN_WHEN_ABSENT),
 ('ai_door_key',dispo.FLAG_AI_DOOR_KEY),('ai_chest_key',dispo.FLAG_AI_CHEST_KEY),
 ('no_bridge_cover',dispo.FLAG_BRIDGE_BARRIER))
_ITEM_FLAG_COLUMNS=(('drops',dispo.ITEM_FLAG_DROP),('ignore_first_playthrough',dispo.ITEM_FLAG_RING))


def _dispo_columns(dialect='fe9'):
 """Export columns: the record's fields in a readable form. Weapons are items 1-4,
 other items 5-8 (the slots the game uses); unread fields are left out."""
 cols=[]
 for i,name in enumerate(DISPO_FIELDS):
  if i not in dispo.FIELD_NAMES or name=='flags' or name.endswith('_flag'):
   continue
  if name.startswith('item') and name[4:].isdigit():
   slot=int(name[4:])
   cols.append((f'{"weapon" if slot<4 else "item"}{slot%4+1}',('field',i)))
   for flag_name,mask in _ITEM_FLAG_COLUMNS:
    cols.append((f'{"weapon" if slot<4 else "item"}{slot%4+1}_{flag_name}',('bit',dispo.FIELD[f'item{slot}_flag'],mask)))
   continue
  cols.append((name,('field',i)))
  if name=='faction':
   cols+=[(flag_name,('bit',dispo.FIELD['flags'],mask)) for flag_name,mask in _UNIT_FLAG_COLUMNS]
 if dialect=='fe10':
  cols.append(('use_fe10growth_stats',('bit',dispo.FE10_GROWTH_FLAGS_FIELD,
                                        dispo.FE10_GROWTH_TABLE)))
 return cols


DISPO_COLUMNS=_dispo_columns()


def dispo_columns(dialect='fe9'):
 """Readable deployment columns for one game's unit-record layout."""
 return _dispo_columns(dialect)
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
def _part(target):
 # a relationship target is relative to xl/ (Excel) or absolute from the package root (/xl/..., other tools)
 return target.lstrip('/') if target.startswith('/') else 'xl/'+target
def _text(node):
 # an inline or shared string: plain <t>, or rich-text runs <r><t>..</t></r>
 return ''.join(t.text or '' for t in node.iter(f'{{{MAIN}}}t'))
def read_workbook(path):
 with zipfile.ZipFile(Path(path)) as z:
  wb=ET.fromstring(z.read('xl/workbook.xml')); rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels')); targets={r.attrib['Id']:r.attrib['Target'] for r in rels}; result={}
  # Excel saves every text cell as an index into the shared strings (t="s")
  shared_part=next((_part(r.attrib['Target']) for r in rels if r.attrib.get('Type','').endswith('/sharedStrings')),'xl/sharedStrings.xml')
  shared=[_text(si) for si in ET.fromstring(z.read(shared_part)).findall(f'{{{MAIN}}}si')] if shared_part in z.namelist() else []
  for sheet in wb.find(f'{{{MAIN}}}sheets'):
   root=ET.fromstring(z.read(_part(targets[sheet.attrib[f'{{{REL}}}id']]))); rows=[]
   for row in root.findall(f'.//{{{MAIN}}}row'):
    vals=[]
    for cell in row.findall(f'{{{MAIN}}}c'):
     i=_col(cell.attrib['r'])
     while len(vals)<=i: vals.append(None)
     kind=cell.attrib.get('t')
     if kind=='inlineStr': n=cell.find(f'{{{MAIN}}}is'); v=_text(n) if n is not None else ''
     elif kind=='s': n=cell.find(f'{{{MAIN}}}v'); v=shared[int(n.text)] if n is not None and n.text else None
     elif kind in ('str','e'): n=cell.find(f'{{{MAIN}}}v'); v=n.text if n is not None else None
     elif kind=='b': n=cell.find(f'{{{MAIN}}}v'); v=int(n.text) if n is not None and n.text else None
     else:
      n=cell.find(f'{{{MAIN}}}v'); v=n.text if n is not None else None
      if v is not None:
       try: v=int(v) if re.fullmatch(r'-?\d+',v) else float(v)
       except ValueError: pass
     vals[i]=v
    rows.append(vals)
   result[sheet.attrib['name']]=rows
  return result


FE10_GROWTH_SHEET='Growth'
FE10_GROWTH_COLUMNS=('index','pid','level',*fe10growth.STAT_NAMES)


def export_fe10_growth(path,data):
 """Export every FE10Growth internal-level line to one editable worksheet."""
 rows=[list(FE10_GROWTH_COLUMNS)]
 for record in fe10growth.read_growth(data):
  for line,stats in enumerate(record.lines):
   rows.append([record.index,record.pid,record.level_of(line),*stats])
 write_workbook(path,{FE10_GROWTH_SHEET:rows})


def import_fe10_growth(path,data):
 """Import FE10Growth stat lines atomically.

 Shared physical lines may appear once for each alias record in an exported
 workbook. Unchanged aliases are ignored; conflicting edits to the same shared
 line are rejected instead of depending on worksheet order.
 """
 sheets=read_workbook(path)
 rows=sheets.get(FE10_GROWTH_SHEET)
 if not rows:
  return data,[f'Expected a {FE10_GROWTH_SHEET} worksheet with a header row.'],0
 cols={str(v).strip().casefold():i for i,v in enumerate(rows[0]) if v is not None}
 required=('index','pid','level')
 missing=[field for field in required if field not in cols]
 stat_columns=[(i,name,cols.get(name.casefold())) for i,name in enumerate(fe10growth.STAT_NAMES)]
 if missing:
  return data,[f'{FE10_GROWTH_SHEET}: missing {", ".join(missing)} column(s)'],0
 if not any(column is not None for _i,_name,column in stat_columns):
  return data,[f'{FE10_GROWTH_SHEET}: no editable stat columns found'],0

 records=fe10growth.read_growth(data)
 seen=set(); changes={}; errors=[]
 for rn,row in enumerate(rows[1:],2):
  if not any(v not in (None,'') for v in row):
   continue
  try:
   index=_num(row[cols['index']] if cols['index']<len(row) else None,'index')
   level=_num(row[cols['level']] if cols['level']<len(row) else None,'level')
   if index is None or not 0<=index<len(records):
    raise ValueError(f'unknown growth record index {index}')
   record=records[index]
   pid=str(row[cols['pid']] if cols['pid']<len(row) else '').strip()
   if pid != record.pid:
    raise ValueError(f'index {index} is {record.pid}, not {pid or "blank"}')
   if level is None or not record.first<=level<=record.last:
    raise ValueError(f'{record.pid} has levels {record.first}-{record.last}, not {level}')
   identity=(index,level)
   if identity in seen:
    raise ValueError(f'duplicate record {index}, level {level}')
   seen.add(identity)
   original=record.lines[level-record.first]
   proposed=list(original)
   for stat_index,stat,column in stat_columns:
    if column is None or column>=len(row) or row[column] in (None,''):
     continue
    value=_num(row[column],stat)
    if value is None or not 0<=value<=255:
     raise ValueError(f'{stat} must be between 0 and 255')
    proposed[stat_index]=value
   if proposed==original:
    continue
   address=record.lines_at+fe10growth.LINE_SIZE*(level-record.first)
   previous=changes.get(address)
   if previous is not None and previous!=proposed:
    raise ValueError(f'conflicting edits to a stat line shared with another record')
   changes[address]=proposed
  except (ValueError,TypeError,IndexError,KeyError) as exc:
   errors.append(f'{FE10_GROWTH_SHEET} row {rn}: {exc}')
 if errors:
  return data,errors,0
 out=bytearray(data)
 for address,stats in changes.items():
  out[address:address+fe10growth.LINE_SIZE]=bytes(stats)
 return bytes(out),[],len(changes)


def export_fe8(path,data,docs=None,only=None):
 if only is not None and only not in FE8_SHEETS:
  raise ValueError(f'Unsupported Excel sheet: {only}')
 f=fe8data.read_fe8data(data) if data and only!='Terrain' else None; sheets={}
 if f:
  if only in (None,'Characters'):
   sheets['Characters']=[['index',*CHARACTER_FIELDS]]+[[r.index,*_flat(r,CHARACTER_FIELDS)] for r in f.characters]
  if only in (None,'Items'):
   sheets['Items']=[['index',*ITEM_FIELDS]]+[[r.index,*_flat(r,ITEM_FIELDS)] for r in f.items]
 if data and only in (None,'Terrain'):
  sheets['Terrain']=[['index',*TERRAIN_FIELDS]]+[[t.index,t.name,t.name_key,t.avoid,t.defense,t.resistance,*t.alt_bonus,t.heal,t.flag7,*t.move_costs] for t in fe8data.read_terrain_types(data)]
 if docs:
  for name,doc in docs.items():
   columns=dispo_columns(doc.dialect)
   headers=['section','unit_index','linked_label',*(field for field,_how in columns)]
   rows=[headers]
   for s in doc.sections:
    if s.is_link: rows.append([s.name,'',s.header,*(['']*len(columns))])
    else:
     for i,u in enumerate(s.units):
      rows.append([s.name,i,'',*(u[how[1]] if how[0]=='field' else ('yes' if u[how[1]]&how[2] else '')
                                 for _field,how in columns)])
   sheets['Dispo '+name.removeprefix('dispos_').removesuffix('.bin')]=rows
 write_workbook(path,sheets)
def _pointer(v):
 """A label cell: 0 is an empty pointer, anything else a label."""
 return 0 if v==0 or str(v).strip()=='0' else str(v).strip()
def _num(v,field):
 if v in (None,''): return None
 try: return int(v)
 except (TypeError,ValueError): raise ValueError(f'{field} must be a whole number') from None
def import_fe8(path,data,docs=None,only=None):
 if only is not None and only not in FE8_SHEETS:
  raise ValueError(f'Unsupported Excel sheet: {only}')
 sheets=read_workbook(path); parsed=fe8data.read_fe8data(data) if data and only!='Terrain' else None; errors=[]; out=data
 if only is not None and only not in sheets:
  return data,docs,[f'Expected a {only} worksheet; this workbook does not contain one.']
 if only is not None and not sheets[only]:
  return data,docs,[f'{only}: missing header row']
 for name,records,fields,patcher in ((('Characters',parsed.characters,CHARACTER_FIELDS,fe8data.patch_character_field),('Items',parsed.items,ITEM_FIELDS,fe8data.patch_item_field)) if parsed else ()):
  if only is not None and name != only:
   continue
  rows=sheets.get(name)
  if not rows: continue
  cols={str(v).strip().casefold():i for i,v in enumerate(rows[0]) if v is not None}
  if 'index' not in cols: errors.append(f'{name}: missing index column'); continue
  if not any(_column(cols,field) is not None for field in fields):
   errors.append(f'{name}: no editable columns found'); continue
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
   columns=dispo_columns(doc.dialect)
   rows=sheets.get('Dispo '+name.removeprefix('dispos_').removesuffix('.bin')); cols={str(v).strip().casefold():i for i,v in enumerate(rows[0])} if rows else {}
   for rn,row in enumerate(rows[1:],2) if rows else []:
    try:
     s=doc.section(str(row[cols['section']])); i=row[cols['unit_index']] if cols['unit_index']<len(row) else ''
     if s is None: raise ValueError('unknown section')
     if i in ('',None):
      if row[cols['linked_label']] not in ('',None): s.header=str(row[cols['linked_label']])
     else:
      u=s.units[int(i)]
      for fi,field in enumerate(DISPO_FIELDS):  # raw columns (older exports)
       if field in cols and cols[field]<len(row) and row[cols[field]] not in ('',None):
        pointer=fi in dispo.POINTER_FIELDS and not (doc.dialect=='fe10' and fi==dispo.FE10_GROWTH_FLAGS_FIELD)
        u[fi]=_pointer(row[cols[field]]) if pointer else _num(row[cols[field]],field)
      for field,how in columns:
       if field not in cols or field in DISPO_FIELDS:
        continue
       v=row[cols[field]] if cols[field]<len(row) else None
       if how[0]=='field':
        if v not in ('',None): u[how[1]]=_pointer(v) if how[1] in dispo.POINTER_FIELDS else _num(v,field)
       else:
        on=str(v).strip().casefold() in ('yes','y','true','1','x') if v not in ('',None) else False
        u[how[1]]=(u[how[1]]|how[2]) if on else (u[how[1]]&~how[2])
    except (ValueError,TypeError,IndexError,KeyError) as e: errors.append(f'{name} row {rn}: {e}')
 if data and only in (None,'Terrain') and 'Terrain' in sheets:
  out,terrain_errors=_import_terrain(sheets['Terrain'],out)
  errors.extend(terrain_errors)
 return (data if errors else out),docs,errors


def _import_terrain(rows,data):
 if not rows:
  return data,['Terrain: missing header row']
 cols={str(v).strip().casefold():i for i,v in enumerate(rows[0]) if v is not None}
 if 'index' not in cols:
  return data,['Terrain: missing index column']
 if not any(field in cols for field in TERRAIN_FIELDS):
  return data,['Terrain: no editable columns found']
 original=fe8data.read_terrain_types(data)
 updates={}; errors=[]
 signed={'avoid','defense','resistance','alt_avoid','alt_defense','alt_resistance'}
 unsigned={'heal','object_tile',*(f'move_cost_{i}' for i in range(len(fe8data.MOVEMENT_TYPE_NAMES)))}
 for rn,row in enumerate(rows[1:],2):
  if not any(v not in (None,'') for v in row): continue
  try:
   index=_num(row[cols['index']] if cols['index']<len(row) else None,'index')
   if index is None or not 0<=index<len(original): raise ValueError('unknown terrain index')
   if index in updates: raise ValueError(f'duplicate terrain index {index}')
   values={}
   for field in TERRAIN_FIELDS:
    col=cols.get(field)
    if col is None or col>=len(row) or row[col] in (None,''): continue
    value=row[col]
    if field in signed or field in unsigned:
     value=_num(value,field)
     low,high=(-128,127) if field in signed else (0,255)
     if not low<=value<=high: raise ValueError(f'{field} must be between {low} and {high}')
    else: value=str(value).strip()
    values[field]=value
   updates[index]=values
  except (ValueError,TypeError) as e: errors.append(f'Terrain row {rn}: {e}')
 if errors: return data,errors
 out=data
 for index,values in updates.items():
  t=fe8data.read_terrain_types(out)[index]
  try:
   if 'name' in values or 'name_key' in values:
    out=fe8data.patch_terrain_names(out,index,name=values.get('name'),name_key=values.get('name_key'))
   block=bytearray(fe8data.terrain_stats_block(t))
   for position,field in enumerate(TERRAIN_FIELDS[2:]):
    if field in values: block[position]=values[field]&0xff
   if bytes(block)!=fe8data.terrain_stats_block(t):
    out=fe8data.patch_terrain_stats(out,index,bytes(block),own_block=len(fe8data.terrain_block_users(out,index))>1)
  except (ValueError,TypeError,IndexError) as e: errors.append(f'Terrain index {index}: {e}')
 return (data if errors else out),errors


#: Radiant Dawn: one sheet per FE10Data.cms table, its columns the table's own fields (fe10data.field_defs).
FE10_SHEETS={'character':'Characters','class':'Classes','item':'Items','skill':'Skills','terrain':'Terrain'}


def _fe10_columns(kind):
 """``(column, field key, field kind)``: the record's fields, then its label lists as comma-separated
 text (skill lists hold mode/label pairs and stay out)."""
 from .formats import fe10data
 cols=[(d.key,d.key,d.kind) for d in fe10data.field_defs(kind)]
 cols+=[(key,key,'list') for k,key in fe10data._LIST_COUNT if k==kind and kind!='skill']
 return cols


def export_fe10(path,data,kind):
 """Export one FE10Data.cms table (``character``, ``class``, ``item``, ``skill``, ``terrain``)."""
 from .formats import fe10data
 cols=_fe10_columns(kind); rows=[['index',*(c for c,_k,_t in cols)]]
 for record in fe10data.read_table(data,kind):
  row=[record.index]
  for _c,key,how in cols:
   value=', '.join(record.lists.get(key,[])) if how=='list' else record.values.get(key)
   row.append(value)
  rows.append(row)
 write_workbook(path,{FE10_SHEETS[kind]:rows})


def import_fe10(path,data,kind):
 """``(file, errors)`` from the sheet of ``kind``: each row names its record by ``index`` and its id,
 and only the cells that differ from the file are written. Nothing is written when any row fails."""
 from .formats import fe10data
 name=FE10_SHEETS[kind]; sheets=read_workbook(path); rows=sheets.get(name)
 if not rows:
  return data,[f'Expected a {name} worksheet with a header row.']
 header={str(v).strip().casefold():i for i,v in enumerate(rows[0]) if v is not None}
 id_key=fe10data.ID_FIELD[kind]
 if 'index' not in header:
  return data,[f'{name}: missing index column']
 cols=[(header[c.casefold()],key,how) for c,key,how in _fe10_columns(kind) if c.casefold() in header]
 if not cols:
  return data,[f'{name}: no editable columns found']
 out=data; errors=[]; count=len(fe10data.read_table(data,kind))
 for rn,row in enumerate(rows[1:],2):
  if not any(v not in (None,'') for v in row): continue
  try:
   index=_num(row[header['index']] if header['index']<len(row) else None,'index')
   if index is None or not 0<=index<count: raise ValueError(f'unknown record index {index}')
   record=fe10data.record(out,kind,index)
   if id_key in header:
    named=row[header[id_key]] if header[id_key]<len(row) else None
    if named not in (None,'') and str(named).strip()!=(record.values.get(id_key) or ''):
     raise ValueError(f'index {index} is {record.values.get(id_key)}, not {named}')
   for col,key,how in cols:
    if key==id_key: continue
    v=row[col] if col<len(row) else None
    if how=='list':
     new=[t for t in (str(v or '').replace(',',' ').split())]
     if new!=record.lists.get(key,[]): out=fe10data.set_list(out,kind,index,key,new); record=fe10data.record(out,kind,index)
     continue
    if how=='label': new=str(v).strip() if v not in (None,'') else None
    elif how=='f32': new=float(v) if v not in (None,'') else None
    else: new=_num(v,key)
    if new is None and how!='label': continue  # an empty number cell keeps the value
    if new!=record.values.get(key):
     out=fe10data.patch_field(out,kind,index,key,new); record=fe10data.record(out,kind,index)
  except (ValueError,TypeError,IndexError,KeyError,OverflowError) as e: errors.append(f'{name} row {rn}: {e}')
 return (data if errors else out),errors
