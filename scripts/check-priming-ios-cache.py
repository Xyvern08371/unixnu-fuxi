#!/usr/bin/env python3
"""Qualify actual iOS priming compiler/cache execution and exact record export.

No user shader executes in the software peer. All production root, native GPU
mapping/presentation and complete UI/deadline requirements remain independent.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
from ios_cache_evidence import ROOT, load, require, sha, validate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage-dir', type=Path, required=True)
parser.add_argument('--observation', type=Path, required=True)
parser.add_argument('--export', type=Path, required=True)
args = parser.parse_args()
work = args.export.resolve()
require(not work.exists(), 'Preserve the existing record export')
require(shutil.disk_usage(ROOT).free > 5 * 1024**3 + 128 * 1024**2, 'Preserve 5 GiB and bounded allowance')
checked = validate(args.stage_dir,args.observation)
s,d,u = checked['stage'],checked['observation'],checked['user']
require(s['record_kind']=='device-priming','Exact priming instrument kind')
first = s['first_consumer_only'];count=3 if first else 4
require(int(u['cpsr'],16)&31==0 and u['instruction_bytes'].startswith('000020d4'),'Actual own EL0 checkpoint')
m = u['register_memory'];raw=bytes.fromhex(m['d:180']['bytes'])
require(len(raw)==384,'Complete bounded parent ledger');v=struct.unpack('<48Q',raw)
require(v[:6]==((0x5052494d494f5332 if first else 0x5052494d494f5331),0,1,4096,4096,count) and
        v[6]==(384 if first else 128) and v[7]==9670832 and v[8]==1 and v[9]==v[10] and v[45]==(2 if first else 1) and v[47]==1,
        'Actual parent mode/ABI, single record and completed sync checkpoint')
pids=[v[12+3*i] for i in range(count)]
require(len(set(pids))==count and all(pid>1 for pid in pids) and all(v[13+3*i]==v[14+3*i]==0 for i in range(count)) and
        (not first or v[21:24]==(0,0,0)),'Distinct successful original-runtime processes; no extra producer slot')
require(v[38]&33==33 and v[39]==v[41]!=v[40]==v[42] and v[43:45]==(1,1),'Actual readonly view, exact own RAM volume and original lower metadata')
summary_memory=bytes.fromhex(m['e:1000']['bytes']);require(len(summary_memory)>=v[6],'Complete bounded manifest')
summary=summary_memory[:128];words=struct.unpack('<16Q',summary)
require(words[0]==0x515455495041434b and words[1]==v[10] and words[6]==1 and words[7]==v[9] and
        summary[96:128].hex()=='606f913adf520420f9b4bb666efb782a68c830f082f1e559e17b20d0d13adbc9','Actual original library and priming manifest')
if first:
    previous_path=ROOT/s['initial_pack_report_relative'];require(sha(previous_path)==s['initial_pack_report_sha256'],'Exact previously verified native priming export')
    previous=load(previous_path)
    require(v[46]==1 and summary_memory[256:384]==summary and summary[16:48].hex()==s['initial_record_sha256']==previous['cache_record_sha256'] and
            summary[64:96].hex()==s['initial_cache_manifest_sha256']==previous['cache_manifest_sha256'] and s['producer_runs_in_boot']==0,
            'Actual pre-worker initial pack equals final bytes and the earlier exact iOS producer record')
worker_memory=bytes.fromhex(m['f:1000']['bytes']);require(0<v[11]<4095 and v[11]<=len(worker_memory),'Complete untruncated worker output')
output=worker_memory[:v[11]].decode('ascii')
pattern=re.compile(r'^PASS: device priming (\S+) pid=(\d+) compute=(\d+)/(\d+)/(\d+)/(\d+)/(\d+) graphics=(\d+)/(\d+)/(\d+)/(\d+)/(\d+) uuid_mutations=(\d+) submissions=(\d+) live=0; software peer, no shader execution$',re.M)
rows=pattern.findall(output)
expected=['consume','uuid-miss','cold-miss'] if first else ['cold-miss','produce','consume','uuid-miss']
require(len(rows)==count and [row[0] for row in rows]==expected,'Complete actual ordered priming ledger; first mode is not relabelled')
fields=['pid','compute_calls','compute_success','compute_required','compute_valid','compute_hits','graphics_calls','graphics_success','graphics_required','graphics_valid','graphics_hits','uuid_mutations','submissions']
cases={row[0]:dict(zip(fields,map(int,row[1:]))) for row in rows}
require([case['pid'] for case in cases.values()]==pids,'Actual logged PID and spawn correspondence')
for mode,case in cases.items():
    require(case['submissions']==1 and case['compute_calls']==1,'Every case retains real priming; observed non-generated compute shape')
    if mode in ('cold-miss','uuid-miss'):
        require(case['compute_success']==0 and case['compute_required']==1 and case['compute_valid']==case['compute_hits']==case['graphics_calls']==0,
                'Actual compile-forbidden refusal, never silent compilation')
        require(case['uuid_mutations']>0 if mode=='uuid-miss' else case['uuid_mutations']==0,'Actual UUID and empty-cache controls are distinct')
    else:
        require(case['compute_success']==case['compute_valid']==case['graphics_calls']==case['graphics_success']==case['graphics_valid']==1 and
                case['compute_required']==case['graphics_required']==0,'Both actual helpers succeed with valid feedback')
        require(case['compute_hits']==case['graphics_hits']==(1 if mode=='consume' else 0),'Both helpers actually hit in the strict consumer, not the cold producer')
require(not first or cases['consume']['pid']==pids[0],'The first actual child is the consumer, with no producer during this boot')
capture=d['scratch_data_snapshot'];observation=args.observation.resolve();snapshot=observation/capture['file']
require(capture['file']=='scratch-data-snapshot.apfs' and capture['read_only'] and capture['bytes']==s['data_bytes']==64*1024**2 and sha(snapshot)==capture['sha256'],
        'Exact bounded paused own Data export')
work.mkdir(parents=True);mount=args.stage_dir.resolve()/'snapshot-mount';mount.mkdir(exist_ok=True)
attached=plistlib.loads(subprocess.check_output(['hdiutil','attach','-readonly','-imagekey','diskimage-class=CRawDiskImage','-nobrowse','-owners','off','-mountpoint',str(mount),'-plist',str(snapshot)],timeout=30))
physical=attached['system-entities'][0]['dev-entry'];manifest={}
try:
    info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(mount)],timeout=10))
    require(info['VolumeUUID']==s['data_volume_uuid'] and info['BusProtocol']=='Disk Image','Actual captured own volume')
    directory,duplicate=mount/'tmp/priming.cache',mount/'tmp/priming.archive'
    require(duplicate.stat().st_size==words[1] and sha(duplicate)==summary[16:48].hex(),'Actual diagnostic raw-record copy, not a Metal binary archive')
    digest=hashlib.sha256();records=[]
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(),'No cache symlink')
        if path.is_dir():continue
        require(path.is_file() and path.stat().st_size<=16*1024**2 and len(records)<1,'Single bounded actual cache record')
        name=str(path.relative_to(directory));data=path.read_bytes();name_bytes=name.encode('ascii')
        require(0<len(name_bytes)<=192 and '..' not in name,'Bounded canonical record path')
        manifest[name]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        digest.update(struct.pack('<I',len(name_bytes)));digest.update(name_bytes);digest.update(struct.pack('<Q',len(data)));digest.update(hashlib.sha256(data).digest());records.append((name,data))
    require(len(records)==1 and len(records[0][1])==words[7] and digest.digest()==summary[64:96],'Every exported record byte matches the actual iOS parent manifest')
    name,data=records[0]
    require(duplicate.read_bytes()==data and data.startswith(b'M2VPPLC\0') and len(data)>=108 and hashlib.sha256(data[:-32]).digest()==data[-32:],'Actual complete framed driver data and checksum')
    length=struct.unpack_from('<Q',data,36)[0]
    require(len(data)==44+length+32 and struct.unpack_from('<2I',data,44)==(32,1) and data[8:16]==data[52:60] and data[20:36]==data[60:76],
            'Actual matching driver identity and complete Vulkan header')
    if first:require(data[20:36].hex()==previous['actual_pipeline_cache_uuid'],'First consumer retains exact target-build cache UUID')
    shutil.copyfile(duplicate,work/'priming.record');shutil.copytree(directory,work/'cache')
finally:subprocess.run(['hdiutil','detach',physical],capture_output=True,check=True,timeout=30)
require(sha(snapshot)==capture['sha256'],'Snapshot unchanged by readonly extraction')
(work/'worker-output.log').write_text(output)
report=dict(evidence='actual original iOS runtime in offline QEMU, real Turnip/IR3 startup cache, software peer executes no shader',
    checker_sha256=sha(Path(__file__)),evidence_module_sha256=sha(ROOT/'scripts/ios_cache_evidence.py'),**{key:checked[key] for key in ['stage_report_sha256','observation_sha256','candidate_sha256']},
    ios_driver_input_sha256=s['driver_input_sha256'],ios_driver_uuid=s['driver_identity']['macho_uuid'],ios_bridge_sha256=s['ios_bridge_sha256'],
    runtime_base_revision=s['runtime_base_revision'],runtime_patches_sha256=s['runtime_patches_sha256'],snapshot_sha256=capture['sha256'],
    cache_manifest=manifest,cache_manifest_sha256=summary[64:96].hex(),cache_record_sha256=summary[16:48].hex(),cache_record_bytes=words[1],
    actual_pipeline_cache_uuid=data[20:36].hex(),worker_pids=pids,cases=cases,actual_ios_priming_cache_hit=True,
    actual_native_cpu_4k=True,worker_page_abi_4k_count=count,worker_live_tcr_sampled=False,original_signatures_amfi_trust_preserved=True,
    readonly_own_extension_view=True,mutable_test_backing=True,parent_called_sync=True,extracted_record_matches_guest_manifest=True,
    selected_priming_initial_image_consumer_qualified=first,producer_runs_in_boot=0 if first else 1,generated_commands_qualified=False,
    original_os_modified=False,production_root_authorization=False,whole_snapshot_fs_consistency_qualified=False,shader_execution=False,physical_device_tested=False,
    active_native_adreno_4k=False,complete_ui_variant_coverage=False,hardware_timing_qualified=False,hardware_ready=False,stable_120_fps_qualified=False)
(work/'checkpoint.json').write_text(json.dumps(report,indent=2)+'\n');(args.stage_dir.resolve()/'priming-cache-checkpoint.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: actual iOS compute/graphics startup helpers both hit with compilation forbidden; cold/UUID controls refuse and all processes release their objects')
print('PASS: complete native priming record exported byte-for-byte against the actual iOS manifest')
if first:print('PASS: initial-image first consumer, no producer in this boot; initial and final record bytes match')
print('No shader execution, complete UI variants, production cache authorization, native GPU4K or stable 120 FPS is qualified')
