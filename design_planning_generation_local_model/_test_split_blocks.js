// 验证 review.html 的 splitBlocks/joinBlocks 逻辑（与页面内实现一致）
function splitBlocks(md) {
    if (!md) return [];
    const lines = md.split('\n');
    const out = [];
    let cur = [];
    let inFence = false;
    for (const line of lines) {
        if (/^\s*(```|~~~)/.test(line)) { inFence = !inFence; cur.push(line); continue; }
        if (inFence) { cur.push(line); continue; }
        if (line.trim() === '') {
            if (cur.length) { out.push(cur.join('\n')); cur = []; }
            continue;
        }
        if (/^\s*#{1,6}\s/.test(line) || /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line.trim())) {
            if (cur.length) { out.push(cur.join('\n')); cur = []; }
            out.push(line.trim());
            continue;
        }
        cur.push(line);
    }
    if (cur.length) out.push(cur.join('\n'));
    return out;
}
function joinBlocks(list) {
    return (list || []).join('\n\n');
}

let failures = 0;
function check(name, cond) {
    console.log((cond ? 'PASS' : 'FAIL') + ' - ' + name);
    if (!cond) failures++;
}

// 样例1: 标题+段落+表格+列表+代码块
const md1 = [
    '## 1.1 概述',
    '',
    '本产品为贴敷式胰岛素泵，用于持续皮下输注胰岛素。',
    '',
    '| 项目 | 内容 |',
    '|------|------|',
    '| 型号 | Pump-X |',
    '| 电源 | 3V 电池 |',
    '',
    '- 列表项一',
    '- 列表项二',
    '',
    '```',
    'code line 1',
    'code line 2',
    '```',
    '',
    '结尾段落。',
].join('\n');

const blocks1 = splitBlocks(md1);
console.log('--- 块数量(期望6):', blocks1.length);
check('块数量=6', blocks1.length === 6);
check('块0=标题', blocks1[0] === '## 1.1 概述');
check('块1=段落', blocks1[1] === '本产品为贴敷式胰岛素泵，用于持续皮下输注胰岛素。');
check('块2=表格(保持多行一体)', blocks1[2].includes('| 型号 | Pump-X |') && blocks1[2].includes('|------|------|'));
check('块3=列表(连续行一体)', blocks1[3] === '- 列表项一\n- 列表项二');
check('块4=代码围栏(保持一体)', blocks1[4] === '```\ncode line 1\ncode line 2\n```');
check('块5=结尾段落', blocks1[5] === '结尾段落。');
check('join 可逆(含标题/段落/表格/代码)', joinBlocks(blocks1) === md1);

// 样例2: 空章节 / 无空行的连续标题+正文
check('空内容 → []', Array.isArray(splitBlocks('')) && splitBlocks('').length === 0);
check('空章节 join=空串', joinBlocks([]) === '');

// 样例3: 标题紧贴正文(无空行) 仍拆分为独立块
const md3 = '## 2.1 范围\n本部分描述适用范围。';
const blocks3 = splitBlocks(md3);
check('无空行标题正文拆分=2块', blocks3.length === 2);
check('块0=标题', blocks3[0] === '## 2.1 范围');
check('块1=正文', blocks3[1] === '本部分描述适用范围。');

// 样例4: 列表项间有空行 → 各自成块（可单独编辑）
const md4 = '- 条目A\n\n- 条目B';
const blocks4 = splitBlocks(md4);
check('空行分隔列表拆=2块', blocks4.length === 2);
check('join 还原', joinBlocks(blocks4) === md4);

// 样例5: 删除一个块后 join
const b5 = splitBlocks(md1);
b5.splice(1, 1); // 删除"块1=段落"
const joined5 = joinBlocks(b5);
check('删除块后不再包含被删文本', !joined5.includes('本产品为贴敷式胰岛素泵'));
check('删除块后标题仍是首块', joined5.startsWith('## 1.1 概述'));

console.log(failures === 0 ? '\nALL BLOCK TESTS PASSED' : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
