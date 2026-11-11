"""Version 2 functional evaluator: immutable generated logic, explicit interface audit."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import time

VERSION = '2.0.2'
FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617
LANG_KEYS = {'Python':'py', 'Go':'go', 'Rust':'rs', 'Java':'jv'}

class InputInterfaceError(ValueError):
    """The generated main signature cannot accept the source program's arguments."""

def load(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]

def strip_comments(code):
    # Keep strings intact, so quoted include paths are never interpreted as comments.
    return re.sub(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*',
                  lambda m: m[0] if m[0].startswith('"') else ' ' + '\n'*m[0].count('\n'), code, flags=re.S)

def main_interface(code):
    code = strip_comments(code)
    main = re.search(r'\bcomponent\s+main\b[^;]*?=\s*(\w+)\s*\(', code)
    if not main: raise ValueError('No main component; evaluator never injects one')
    template = re.search(r'\btemplate\s+'+re.escape(main[1])+r'\s*\([^)]*\)\s*\{', code)
    if not template: raise ValueError('Main template definition not found in generated source')
    begin, end, depth = template.end(), template.end(), 1
    while depth and end < len(code):
        depth += (code[end] == '{') - (code[end] == '}')
        end += 1
    if depth: raise ValueError('Unbalanced main template body')
    body = code[begin:end-1]
    result = {}
    for direction in ('input', 'output'):
        declarations = re.findall(r'\bsignal\s+'+direction+r'\s+([^;]+);', body)
        names = []
        for block in declarations:
            block = re.sub(r'\{[^{}]*\}', '', block)
            for part in block.split(','):
                name = re.sub(r'\[[^]]*\]', '', part).strip()
                if not re.fullmatch(r'[A-Za-z_]\w*', name): raise ValueError('Unsupported signal declaration: '+part)
                names.append(name)
        if len(set(names)) != len(names): raise ValueError('Duplicate main signal name')
        result[direction] = names
    if not result['output']: raise ValueError('No main output signal')
    return result

def source_parameters(task):
    lang = task['source_lang']
    source = task['source_code']
    if lang == 'Python':
        node = next(n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        return [a.arg for a in node.args.posonlyargs + node.args.args]
    if lang == 'Go':
        signature = re.search(r'func\s*(?:\([^)]*\)\s*)?\w+\s*\(([^)]*)\)', source)
        if not signature: raise ValueError('Cannot resolve Go signature')
        return [p.strip().split()[0] for p in signature[1].split(',') if p.strip()]
    if lang == 'Rust':
        signature = re.search(r'fn\s+\w+\s*\(([^)]*)\)', source)
        if not signature: raise ValueError('Cannot resolve Rust signature')
        return [p.split(':')[0].strip() for p in signature[1].split(',') if p.strip()]
    signature = re.search(r'\w+\s*\(([^)]*)\)', source)
    if not signature: raise ValueError('Cannot resolve Java signature')
    return [p.strip().split()[-1] for p in signature[1].split(',') if p.strip()]

def resolve_library_paths(code):
    rewrites = []
    # Rewrite only the quoted literal, leaving comments and all program logic unchanged.
    # Comment stripping changes offsets, so process original tokens while skipping comments.
    token = re.compile(r'/\*.*?\*/|//[^\n]*|\binclude\s+"([^"]+)"\s*;', re.S)
    def replace(m):
        if m[1] is None: return m[0]
        path = m[1]
        normalized = path.replace('\\', '/')
        if 'circomlib' in normalized and '/circuits/' in normalized:
            normalized = normalized.split('/circuits/', 1)[1]
        if normalized.startswith('/') or '..' in Path(normalized).parts or ':' in normalized:
            raise ValueError('Include outside configured library: '+path)
        if normalized != path: rewrites.append({'from':path,'to':normalized})
        return 'include "'+normalized+'";'
    return token.sub(replace, code), rewrites

def run_command(argv, work, label, timeout=120):
    started = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=work, capture_output=True, text=True, timeout=timeout)
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        def text(v): return v.decode(errors='replace') if isinstance(v, bytes) else v or ''
        code, stdout, stderr = 124, text(error.stdout), text(error.stderr)+'\nTimeout'
    (work/(label+'.stdout.log')).write_text(stdout)
    (work/(label+'.stderr.log')).write_text(stderr)
    (work/(label+'.command.json')).write_text(json.dumps({'argv':argv,'exit':code,'elapsed':time.monotonic()-started}))
    return code, stdout, stderr

def read_witness(path, index):
    raw = path.read_bytes()
    if raw[:4] != b'wtns': raise ValueError('Invalid witness magic')
    offset, width, prime = 12, None, None
    for _ in range(struct.unpack_from('<I',raw,8)[0]):
        section, size = struct.unpack_from('<IQ',raw,offset)
        offset += 12
        if section == 1:
            width = struct.unpack_from('<I',raw,offset)[0]
            prime = int.from_bytes(raw[offset+4:offset+4+width],'little')
            count = struct.unpack_from('<I',raw,offset+4+width)[0]
        if section == 2:
            if prime != FIELD or not 0 <= index < count: raise ValueError('Unexpected witness field or output index')
            return int.from_bytes(raw[offset+width*index:offset+width*(index+1)],'little')
        offset += size
    raise ValueError('Witness values section not found')

def symbol_interface(path, interface):
    symbols = {}
    for line in path.read_text().splitlines():
        _, witness_index, _, name = line.split(',',3)
        symbols[name] = int(witness_index)
    dimensions = {}
    for name in interface['input']:
        indexes = [tuple(map(int,re.findall(r'\[(\d+)\]',n))) for n in symbols if re.fullmatch(r'main\.'+re.escape(name)+r'(\[\d+\])*',n)]
        if not indexes: raise ValueError('Compiled input symbol not found: '+name)
        ranks = {len(i) for i in indexes}
        if len(ranks) != 1: raise ValueError('Inconsistent compiled array shape')
        dimensions[name] = tuple(max(i[d] for i in indexes)+1 for d in range(len(indexes[0])))
    name = 'main.'+interface['output'][0]
    candidates = [(tuple(map(int,re.findall(r'\[(\d+)\]',n))),idx,n) for n,idx in symbols.items() if re.fullmatch(re.escape(name)+r'(\[\d+\])*',n)]
    if not candidates: raise ValueError('Compiled main output symbol not found')
    _, index, output_name = min(candidates)
    if index < 0: raise ValueError('Main output has no witness position')
    return dimensions, index, output_name

def reshape(flat, shape):
    if not shape: return str(flat[0])
    if len(shape)==1: return [str(x) for x in flat]
    stride = 1
    for d in shape[1:]: stride *= d
    return [reshape(flat[i*stride:(i+1)*stride],shape[1:]) for i in range(shape[0])]

def flatten(value):
    if isinstance(value,list): return [v for x in value for v in flatten(x)]
    return [value]

def map_inputs(values, names, dimensions, source_names):
    exact_names = len(names)==len(source_names) and set(names)==set(source_names)
    mapping = 'source_names' if exact_names else 'main_declaration_order'
    ordered = [values[source_names.index(n)] for n in names] if exact_names else values
    output, offset = {}, 0
    for name in names:
        shape = dimensions[name]
        size = 1
        for d in shape: size *= d
        if offset >= len(ordered): raise InputInterfaceError('Not enough source arguments for main inputs')
        if isinstance(ordered[offset],list):
            flat = flatten(ordered[offset]); offset += 1
        else:
            flat = ordered[offset:offset+size]; offset += size
        if len(flat)!=size: raise InputInterfaceError('Source argument does not match compiled input shape')
        output[name] = reshape(flat,shape)
    if offset!=len(ordered): raise InputInterfaceError('Unconsumed source arguments')
    return output, mapping

def evaluate_task(task, expected_outputs, lib_path, ptau_path, eval_root, *, proof=False, check_witness=False):
    work = Path(eval_root)
    work.mkdir(parents=True,exist_ok=False)
    code = task.get('translated_circom','')
    report = {'id':task['id'],'func':task['func_name'],'lang':task['source_lang'],'status':'EVAL_ERROR',
              'compile_success':False,'constraints':None,'proving_time_ms':None,'proof_size_bytes':None,
              'proof_evaluated':proof,'test_cases':[],'error_msg':'','evaluator_version':VERSION,
              'source_sha256':hashlib.sha256(code.encode()).hexdigest(),'work_dir':str(work)}
    for field in ('agent_status','candidate_source'):
        if field in task: report[field]=task[field]
    try:
        (work/'original.circom').write_text(code)
        try: resolved, rewrites = resolve_library_paths(code)
        except ValueError as error:
            report.update(status='COMPILE_FAIL',error_msg=str(error)); return report
        report['include_path_rewrites']=rewrites
        (work/'circuit.circom').write_text(resolved)
        ret, stdout, stderr = run_command(['circom','circuit.circom','--r1cs','--wasm','--sym','-l',str(lib_path)],work,'compile')
        if ret:
            report.update(status='COMPILE_FAIL',error_msg=stderr); return report
        if not (work/'circuit.r1cs').exists() or not (work/'circuit_js/circuit.wasm').exists():
            raise ValueError('Compiler returned success without required artifacts')
        report['compile_success']=True
        try:
            interface=main_interface(resolved)
            params=source_parameters(task)
            dimensions, output_index, output_name=symbol_interface(work/'circuit.sym',interface)
        except (InputInterfaceError, ValueError) as error:
            report.update(status='INTERFACE_FAIL',error_msg=str(error)); return report
        report.update(main_inputs=interface['input'],source_parameters=params,output_signal=output_name,
                      output_witness_index=output_index,input_dimensions=dimensions)
        linear=re.search(r'(?:^|\n)\s*linear constraints:\s*(\d+)',stdout)
        nonlinear=re.search(r'non-linear constraints:\s*(\d+)',stdout)
        if linear and nonlinear: report['constraints']=int(linear[1])+int(nonlinear[1])
        proof_ready=False
        if proof:
            for label,argv in [('setup',['snarkjs','groth16','setup','circuit.r1cs',str(ptau_path),'initial.zkey']),
                               ('contribute',['snarkjs','zkey','contribute','initial.zkey','final.zkey','--name=Evaluation','-e=offline-evaluation']),
                               ('verification-key',['snarkjs','zkey','export','verificationkey','final.zkey','verification-key.json'])]:
                ret,_,err=run_command(argv,work,label)
                if ret:
                    report['proof_error']=err; break
            else: proof_ready=True
        for i,(values,expected) in enumerate(zip(task['inputs'],expected_outputs)):
            if not isinstance(expected,int) or abs(expected)>=FIELD//2: raise ValueError('Truth outside signed integer comparison domain')
            try:
                inputs, binding=map_inputs(values,interface['input'],dimensions,params)
            except InputInterfaceError as error:
                report['test_cases'].append({'input':values,'expected':expected,'actual':None,'actual_field':None,
                                             'status':'FAIL','failure':'INTERFACE_FAIL','error_msg':str(error)})
                continue
            report['input_binding']=binding
            (work/f'input-{i}.json').write_text(json.dumps(inputs))
            case={'input':values,'mapped_input':inputs,'expected':expected,'actual':None,'actual_field':None,'status':'FAIL'}
            ret,_,err=run_command(['node','circuit_js/generate_witness.js','circuit_js/circuit.wasm',f'input-{i}.json',f'witness-{i}.wtns'],work,f'witness-{i}',timeout=30)
            if ret: case.update(failure='WITNESS_FAIL',error_msg=err)
            else:
                actual_field=read_witness(work/f'witness-{i}.wtns',output_index)
                actual=actual_field-FIELD if actual_field>FIELD//2 else actual_field
                case.update(actual=actual,actual_field=actual_field,status='PASS' if actual==expected else 'FAIL')
                if check_witness:
                    ret,_,err=run_command(['snarkjs','wtns','check','circuit.r1cs',f'witness-{i}.wtns'],work,f'constraint-check-{i}')
                    case['constraint_check_success']=ret==0
                    if ret: case.update(status='FAIL',failure='CONSTRAINT_FAIL',error_msg=err)
                if proof_ready and case['status']=='PASS' and report['proving_time_ms'] is None:
                    started=time.monotonic()
                    ret,_,err=run_command(['snarkjs','groth16','prove','final.zkey',f'witness-{i}.wtns','proof.json','public.json'],work,'prove')
                    if ret: report['proof_error']=err
                    else:
                        report['proving_time_ms']=round((time.monotonic()-started)*1000)
                        report['proof_size_bytes']=(work/'proof.json').stat().st_size
                        ret,_,err=run_command(['snarkjs','groth16','verify','verification-key.json','public.json','proof.json'],work,'verify')
                        report['proof_verified']=ret==0
            report['test_cases'].append(case)
        if len(report['test_cases'])!=len(task['inputs']): raise ValueError('Incomplete test evaluation')
        report['status']='SUCCESS' if all(c['status']=='PASS' for c in report['test_cases']) else 'LOGIC_FAIL'
        if all(c.get('failure')=='INTERFACE_FAIL' for c in report['test_cases']): report['status']='INTERFACE_FAIL'
        if report['status']=='LOGIC_FAIL': report['error_msg']=next((c.get('error_msg','Output mismatch') for c in report['test_cases'] if c['status']!='PASS'),'')
    except Exception as error:
        report.update(status='EVAL_ERROR',error_msg=f'{type(error).__name__}: {error}')
    return report

def summarize(rows, tasks):
    tests=sum(len(t['inputs']) for t in tasks)
    passed=sum(c['status']=='PASS' for r in rows for c in r.get('test_cases',[]))
    compiled=sum(r['compile_success'] for r in rows)
    correct=sum(r['status']=='SUCCESS' for r in rows)
    total=len(tasks)
    return {'total':total,'evaluated':len(rows),'total_tests':tests,'passed_tests':passed,
            'compiled':compiled,'all_pass':correct,'CSR':100*compiled/total,'CA':100*correct/total,
            'PR':100*passed/tests,'statuses':dict(Counter(r['status'] for r in rows)),
            'unresolved_evaluation_errors':sum(r['status']=='EVAL_ERROR' for r in rows)}
