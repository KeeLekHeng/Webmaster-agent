// Trusted parser: website source is parsed as data, never imported or evaluated.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const ts = require(process.env.GUARDIAN_TYPESCRIPT_PATH);
if (ts.version !== '6.0.3') throw new Error('Unreviewed parser version');
const [root, planPath] = process.argv.slice(2);
const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
function fail() { throw new Error('Unsupported mechanical repair'); }
const files = new Map();
for (const edit of plan.edits) {
  if (!/^src\/components\/public\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+\.tsx?$/.test(edit.path)) fail();
  if (!files.has(edit.path)) files.set(edit.path, []);
  files.get(edit.path).push(edit);
}
for (const [name, edits] of files) {
  const file = path.join(root, name);
  const text = fs.readFileSync(file, 'utf8');
  const ast = ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true);
  if (ast.parseDiagnostics.length) fail();
  const patches = [];
  for (const edit of edits) {
    const bindings = new Set();
    const imports = [];
    function collect(node) {
      if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier) && node.moduleSpecifier.text === edit.module) {
        const clause = node.importClause;
        if (clause?.name) bindings.add(clause.name.text);
        if (clause?.namedBindings) {
          if (ts.isNamespaceImport(clause.namedBindings)) bindings.add(clause.namedBindings.name.text);
          else for (const item of clause.namedBindings.elements) { bindings.add(item.name.text); imports.push(item); }
        }
      }
      ts.forEachChild(node, collect);
    }
    collect(ast);
    if (edit.kind !== 'rename_import' && !bindings.has(edit.binding)) fail();
    // Reject shadowing rather than guessing which binding an expression resolves to.
    function shadow(node) {
      if ((ts.isParameter(node) || ts.isVariableDeclaration(node) || ts.isBindingElement(node) ||
           ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) ||
           ts.isClassDeclaration(node) || ts.isClassExpression(node)) && node.name &&
          edit.binding && node.name.getText(ast).match(new RegExp('\\b' + edit.binding.replace(/\$/g,'\\$') + '\\b'))) fail();
      ts.forEachChild(node, shadow);
    }
    shadow(ast);
    const matches = [];
    function at(node) { return ast.getLineAndCharacterOfPosition(node.getStart(ast)).line + 1 === edit.line; }
    function visit(node) {
      if (edit.kind === 'rename_import' && imports.includes(node) && (node.propertyName || node.name).text === edit.old && at(node)) {
        matches.push({start: node.getStart(ast), end: node.end,
          value: `${edit.new} as ${node.name.text}`});
      }
      if (edit.kind === 'rename_member' && ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression) &&
          node.expression.text === edit.binding && node.name.text === edit.old && at(node.name)) {
        matches.push({start: node.name.getStart(ast), end: node.name.end, value: edit.new});
      }
      if (edit.kind === 'rename_jsx_prop' && ts.isJsxAttribute(node) && node.name.text === edit.old && at(node.name)) {
        const element = node.parent.parent;
        if ((ts.isJsxOpeningElement(element) || ts.isJsxSelfClosingElement(element)) &&
            ts.isIdentifier(element.tagName) && element.tagName.text === edit.binding) {
          matches.push({start: node.name.getStart(ast), end: node.name.end, value: edit.new});
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(ast);
    if (matches.length !== 1) fail();
    patches.push(matches[0]);
  }
  patches.sort((a,b) => b.start-a.start);
  let result = text, previous = text.length + 1;
  for (const patch of patches) {
    if (patch.end > previous) fail();
    result = result.slice(0,patch.start) + patch.value + result.slice(patch.end);
    previous = patch.start;
  }
  if (ts.createSourceFile(name,result,ts.ScriptTarget.Latest,true).parseDiagnostics.length) fail();
  fs.writeFileSync(file,result);
}
