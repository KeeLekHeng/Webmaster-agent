// Parse literal public fixture data. Never import/evaluate candidate source.
'use strict';
const fs=require('node:fs');
const ts=require('/opt/guardian-parser/node_modules/typescript');
if(ts.version!=='6.0.3')throw Error('Unreviewed fixture parser');
const text=fs.readFileSync('/work/src/content/blog-content.ts','utf8');
if(Buffer.byteLength(text)>65536)throw Error('Fixture source budget');
const ast=ts.createSourceFile('blog-content.ts',text,ts.ScriptTarget.Latest,true);
let nodes=0;
function literal(node){
  if(++nodes>10000)throw Error('Fixture node budget');
  if(ts.isAsExpression(node)||ts.isSatisfiesExpression(node))return literal(node.expression);
  if(ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node))return node.text;
  if(ts.isNumericLiteral(node))return Number(node.text);
  if(node.kind===ts.SyntaxKind.TrueKeyword)return true;
  if(node.kind===ts.SyntaxKind.FalseKeyword)return false;
  if(node.kind===ts.SyntaxKind.NullKeyword)return null;
  if(ts.isArrayLiteralExpression(node))return node.elements.map(literal);
  if(ts.isObjectLiteralExpression(node)){
    const value=Object.create(null);
    for(const property of node.properties){
      if(!ts.isPropertyAssignment(property)||!(ts.isIdentifier(property.name)||ts.isStringLiteral(property.name)))throw Error('Nonliteral fixture');
      const key=property.name.text;
      if(['__proto__','constructor','prototype'].includes(key)||Object.hasOwn(value,key))throw Error('Unsafe fixture key');
      value[key]=literal(property.initializer);
    }
    return value;
  }
  throw Error('Fixture contains executable expression');
}
let posts;
for(const statement of ast.statements){
  if(ts.isVariableStatement(statement))for(const declaration of statement.declarationList.declarations){
    if(ts.isIdentifier(declaration.name)&&declaration.name.text==='blogPosts'){
      if(posts)throw Error('Duplicate fixture declaration');
      posts=literal(declaration.initializer);
    }
  }
}
if(!Array.isArray(posts)||posts.length<1||posts.length>50)throw Error('Invalid fixture set');
const output=JSON.stringify(posts);
if(Buffer.byteLength(output)>65536)throw Error('Fixture output budget');
process.stdout.write(output);
