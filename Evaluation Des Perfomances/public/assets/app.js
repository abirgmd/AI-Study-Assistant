'use strict';
const $ = selector => document.querySelector(selector);
const csrf = $('meta[name="csrf-token"]').content;
let courses = [];
const now = new Date();
const day = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
function notice(message) { $('#toast').textContent=message; }
async function api(action, options={}) {
 const response=await fetch(`api.php?action=${action}`, {...options,headers:{'X-CSRF-Token':csrf,...(options.headers||{})}});
 if(response.status===401){location.href='login.php';throw new Error('Veuillez vous reconnecter.');}
 let data;try{data=await response.json();}catch{throw new Error('Réponse serveur invalide. Vérifiez PHP et MySQL.');}
 if(!response.ok)throw new Error(data.error||'Une erreur est survenue.');
 return data;
}
function renderCourses(){
 const query=$('#search').value.toLocaleLowerCase('fr');$('#courses').replaceChildren();
 courses.filter(c=>c.name.toLocaleLowerCase('fr').includes(query)).forEach(c=>{
  const row=document.createElement('div');row.className='course';
  const icon=document.createElement('span');icon.className='icon';icon.textContent='▤';
  const box=document.createElement('div');const link=document.createElement('a');link.className='course-link';link.href=`download.php?id=${encodeURIComponent(c.id)}`;link.title='Télécharger ce cours';
  const title=document.createElement('b');title.textContent=c.name;link.append(title);
  const small=document.createElement('small');small.textContent=`${Math.ceil(c.file_size/1024)} Ko · Télécharger`;
  const tag=document.createElement('span');tag.className='tag';tag.textContent=c.type;
  box.append(link,small);row.append(icon,box,tag);$('#courses').append(row);
 });
 if(!$('#courses').children.length)$('#courses').textContent=courses.length?'Aucun cours trouvé.':'Votre espace est prêt. Importez votre premier cours !';
 $('#coursecount').textContent=courses.length;
}
async function loadCourses(){const data=await api('courses');courses=data.courses;renderCourses();}
$('#search').oninput=renderCourses;
$('#import').onclick=()=>$('#file').click();
$('#file').onchange=async event=>{
 const file=event.target.files[0];if(!file)return;
 if(file.size>10*1024*1024){notice('Fichier trop volumineux : 10 Mo maximum.');event.target.value='';return;}
 const body=new FormData();body.append('course',file);$('#import').disabled=true;notice('Import du document en cours…');
 try{const data=await api('upload',{method:'POST',body});await loadCourses();notice(data.message);}catch(e){notice(e.message);}finally{$('#import').disabled=false;event.target.value='';}
};
document.querySelectorAll('[data-tool]').forEach(button=>button.onclick=()=>openTool(button.dataset.tool));
function openTool(name){
 $('#title').textContent=name;$('#fields').replaceChildren();$('#result').textContent='';$('#fields').onchange=null;
 $('#action').hidden=false;$('#action').disabled=false;$('#notice').hidden=true;
 const quiz=name==='Quiz de révision';
 $('#modal').classList.toggle('wide',quiz);
 if(quiz)openQuizHome();
 else if(name==='Recherche intelligente')openSearch();
 else if(name==='Assistant de cours')openAssistant();
 $('#modal').showModal();
}

/* Liste des cours (TXT et DOCX lisibles ; un PDF apparaît désactivé). Retourne null s’il n’y a aucun cours lisible. */
function courseSelectFor(){
 const select=document.createElement('select');select.setAttribute('aria-label','Choisir un cours');
 courses.forEach(c=>{
  const usable=QUIZ_COURSE_RE.test(c.original_name);
  const option=new Option(usable?c.name:`${c.name} (format non pris en charge)`,String(c.id));
  option.disabled=!usable;select.add(option);
 });
 const first=select.querySelector('option:not([disabled])');
 if(!first)return null;
 select.value=first.value;return select;
}

/* ---- Recherche : mots ou notions dans les cours TXT et DOCX (sans IA) ---- */
function openSearch(){
 $('#description').textContent='Tapez un mot ou une notion : les passages de vos cours qui la contiennent apparaissent ici.';
 const input=document.createElement('input');input.type='search';input.placeholder='Ex. : régression';input.setAttribute('aria-label','Votre recherche');
 const hits=document.createElement('div');hits.className='study-hits';
 $('#fields').append(labelled('Recherche',input),hits);
 const action=$('#action');action.textContent='Rechercher';
 const run=async()=>{
  const query=input.value.trim();
  if(query.length<2){$('#result').textContent='Saisissez au moins 2 caractères.';return;}
  action.disabled=true;hits.replaceChildren();$('#result').textContent='Recherche en cours…';
  try{
   const data=await api(`search&q=${encodeURIComponent(query)}`);
   const messages=[data.results.length?`${data.results.length} passage(s) trouvé(s).`:'Aucun passage trouvé.'];
   if(data.skipped)messages.push(`${data.skipped} cours (PDF ou illisible) non pris en compte.`);
   $('#result').textContent=messages.join(' ');
   data.results.forEach(hit=>{
    const card=document.createElement('article');card.className='study-hit';
    const title=document.createElement('b');title.textContent=hit.course_name;
    const text=document.createElement('p');text.textContent=hit.text;
    card.append(title,text);hits.append(card);
   });
  }catch(e){$('#result').textContent=e.message;}
  finally{action.disabled=false;}
 };
 action.onclick=run;
 input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();run();}});
}

/* ---- Assistant de cours : réponse fondée uniquement sur le texte du cours choisi (service IA) ---- */
function openAssistant(){
 $('#description').textContent='Posez une question sur un de vos cours. La réponse s’appuie uniquement sur le texte de ce cours.';
 const select=courseSelectFor();
 if(!select){
  $('#result').textContent=courses.length?'L’assistant lit les cours TXT ou DOCX. Importez un cours de ce type.':'Importez un premier cours (TXT ou DOCX) pour poser une question.';
  $('#action').hidden=true;return;
 }
 const question=document.createElement('textarea');question.rows=3;question.placeholder='Ex. : Quelle est la différence entre classification et régression ?';question.setAttribute('aria-label','Votre question');
 const answer=document.createElement('div');answer.className='study-answer';answer.setAttribute('aria-live','polite');
 $('#fields').append(labelled('1. Cours',select),labelled('2. Votre question',question),answer);
 const action=$('#action');action.textContent='Poser la question';
 action.onclick=async()=>{
  action.disabled=true;answer.textContent='Réponse en cours…';$('#result').textContent='';
  try{
   const data=await api('assistant',{method:'POST',body:new URLSearchParams({course_id:select.value,question:question.value.trim()})});
   answer.textContent=data.answer;$('#result').textContent=data.found_in_course?`Réponse fondée sur « ${data.course_name} ».`:`Cette question ne semble pas traitée dans « ${data.course_name} ».`;
  }catch(e){answer.textContent='';$('#result').textContent=e.message;}
  finally{action.disabled=false;}
 };
}

/* ---- Quiz de révision : génération à partir d’un cours TXT ou DOCX, correction côté navigateur ---- */
const QUIZ_COURSE_RE=/\.(txt|docx)$/i;
const QUIZ_TYPE_NAMES={mcq:'QCM',true_false:'Vrai / faux',flashcard:'Fiches recto/verso',matching:'Questions reliées'};
function quizKindName(questions){
 const types=[...new Set(questions.map(q=>q.image?'image':(q.type||'mcq')))];
 if(types.length>1)return 'Mélange de types';
 return types[0]==='image'?'Questions avec image':(QUIZ_TYPE_NAMES[types[0]]||'Quiz');
}
function labelled(text,control){const label=document.createElement('label');label.className='quiz-label';label.textContent=text;label.append(control);return label;}
/* Ouverture : trois étapes (cours, type, génération). Les types viennent de l’API ; un PDF apparaît désactivé. */
async function openQuizHome(){
 $('#title').textContent='Quiz de révision';
 $('#description').textContent='Trois étapes : choisissez un cours, choisissez le type de quiz, puis générez.';
 $('#fields').replaceChildren();$('#result').textContent='';$('#fields').onchange=null;
 const action=$('#action');action.hidden=false;action.disabled=true;action.textContent='Générer le quiz';
 if(!courses.length){
  $('#result').textContent='Importez un premier cours (TXT ou DOCX) pour générer un quiz.';
  action.hidden=true;
  return;
 }
 const courseSelect=document.createElement('select');courseSelect.setAttribute('aria-label','Choisir un cours');
 courses.forEach(c=>{
  const usable=QUIZ_COURSE_RE.test(c.original_name);
  const option=new Option(usable?c.name:`${c.name} (format non pris en charge)`,String(c.id));
  option.disabled=!usable;courseSelect.add(option);
 });
 const firstUsable=courseSelect.querySelector('option:not([disabled])');
 if(!firstUsable){
  $('#result').textContent='Les quiz se génèrent à partir de cours TXT ou DOCX. Importez un cours de ce type.';
  action.hidden=true;
  return;
 }
 courseSelect.value=firstUsable.value;
 const kindSelect=document.createElement('select');kindSelect.setAttribute('aria-label','Type de quiz');
 kindSelect.disabled=true;kindSelect.add(new Option('Chargement…','',true,true));
 const help=document.createElement('p');help.className='quiz-help';
 const saved=document.createElement('div');
 $('#fields').append(labelled('1. Cours',courseSelect),labelled('2. Type de quiz',kindSelect),help,saved);
 let kinds=[];
 const refresh=()=>{
  const kind=kinds.find(k=>k.value===kindSelect.value);
  help.textContent=kind?kind.help:'';
  const chosen=courseSelect.selectedOptions[0];
  action.disabled=!(kinds.length&&chosen&&!chosen.disabled);
 };
 courseSelect.onchange=refresh;kindSelect.onchange=refresh;
 action.onclick=()=>generateQuiz(courseSelect.value,'5',kindSelect.value);
 try{
  kinds=(await api('quiz_kinds')).kinds;
  kindSelect.replaceChildren();
  kinds.forEach(k=>kindSelect.add(new Option(k.label,k.value)));
  kindSelect.disabled=false;
 }catch(e){
  $('#result').textContent=e.message;
 }
 refresh();
 loadSavedQuizzes(saved);
}
async function generateQuiz(courseId,count,kind='mixed'){
 const action=$('#action');action.disabled=true;$('#fields').classList.add('busy');
 $('#result').textContent='Génération en cours : cela peut prendre quelques dizaines de secondes.';
 try{
  const data=await api('quiz_generate',{method:'POST',body:new URLSearchParams({course_id:courseId,count,kind})});
  const notes=[];
  if(data.rejected)notes.push(`${data.rejected} question(s) incomplète(s) ou incohérente(s) ont été écartées.`);
  if(data.with_image)notes.push(`${data.with_image} question(s) s’appuient sur une image du cours.`);
  if(data.source_truncated)notes.push('Le cours est long : le quiz porte sur sa première partie.');
  showQuiz(data.quiz,notes.join(' '));
 }catch(e){$('#result').textContent=e.message;}
 finally{action.disabled=false;$('#fields').classList.remove('busy');}
}
function showQuiz(quiz,notes=''){
 $('#title').textContent=quiz.title;
 const scored=quiz.questions.some(q=>(q.type||'mcq')!=='flashcard');
 $('#description').textContent=`${quiz.questions.length} éléments tirés de « ${quiz.course_name} ». ${scored?'Répondez à chaque question, puis vérifiez.':'Retournez chaque fiche pour voir sa réponse.'}`;
 $('#fields').replaceChildren();$('#result').textContent=notes;
 const rows=quiz.questions.map((q,i)=>buildItem(q,i));
 const scoredRows=rows.filter(row=>row.scored);
 const head=document.createElement('div');head.className='quiz-head';
 const kind=document.createElement('span');kind.className='quiz-kind';kind.textContent=quizKindName(quiz.questions);
 const progress=document.createElement('div');progress.className='quiz-progress';
 const progressText=document.createElement('span');progressText.className='quiz-progress-text';
 const bar=document.createElement('div');bar.className='quiz-bar';const fill=document.createElement('span');bar.append(fill);
 progress.append(progressText,bar);head.append(kind);
 if(scoredRows.length)head.append(progress);
 const updateProgress=()=>{
  const done=scoredRows.filter(row=>row.answered()).length;
  progressText.textContent=`${done} / ${scoredRows.length} répondues`;
  fill.style.width=`${scoredRows.length?Math.round(done/scoredRows.length*100):0}%`;
 };
 $('#fields').append(head);
 rows.forEach(row=>$('#fields').append(row.node));
 $('#fields').onchange=updateProgress;
 updateProgress();
 const action=$('#action');action.hidden=false;action.disabled=false;
 if(scored){action.textContent='Vérifier mes réponses';action.onclick=()=>correctQuiz(rows,quiz.id);}
 else{action.textContent='Nouveau quiz';action.onclick=openQuizHome;}
}
/* Un élément : bloc HTML + check(), qui le corrige et renvoie true/false, ou null si l’élément n’est pas noté (fiche). */
function buildItem(q,i){
 const kind=q.type||'mcq';
 const node=document.createElement('fieldset');node.className=`quiz-q quiz-kind-${q.image?'image':kind}`;
 const legend=document.createElement('legend');node.append(legend);
 const feedback=document.createElement('p');feedback.className='quiz-feedback';feedback.hidden=true;
 const setFeedback=(ok,message,explanation)=>{feedback.hidden=false;feedback.className=`quiz-feedback ${ok?'ok':'ko'}`;feedback.textContent=`${message} ${explanation}`;};
 if(kind==='flashcard'){
  legend.textContent=`${i+1}. Fiche`;
  const front=document.createElement('p');front.className='flash-front';front.textContent=q.front;
  const back=document.createElement('p');back.className='flash-back';back.textContent=q.back;back.hidden=true;
  const reveal=document.createElement('button');reveal.type='button';reveal.className='textbtn';reveal.textContent='Voir la réponse';reveal.setAttribute('aria-expanded','false');
  reveal.onclick=()=>{const show=back.hidden;back.hidden=!show;reveal.textContent=show?'Masquer la réponse':'Voir la réponse';reveal.setAttribute('aria-expanded',String(show));};
  node.append(front,reveal,back);
  return {node,scored:false,answered:()=>false,value:()=>null,check:()=>null};
 }
 legend.textContent=`${i+1}. ${q.question}`;
 if(q.image){const img=document.createElement('img');img.className='quiz-image';img.alt='Image du cours liée à la question';img.src=q.image;node.append(img);}
 if(kind==='matching'){
  const selects=q.left.map((left,j)=>{
   const row=document.createElement('label');row.className='quiz-match';
   const text=document.createElement('span');text.textContent=left;
   const select=document.createElement('select');select.setAttribute('aria-label',`Correspondance de ${left}`);
   select.add(new Option('Choisissez…',''));
   q.right.forEach((right,k)=>select.add(new Option(right,String(k))));
   row.append(text,select);node.append(row);
   return {row,select,j};
  });
  node.append(feedback);
  return {node,scored:true,answered:()=>selects.some(({select})=>select.value!==''),value:()=>selects.map(({select})=>select.value===''?null:Number(select.value)),check:()=>{
   let good=0;
   selects.forEach(({row,select,j})=>{
    const ok=select.value===String(q.answer[j]);
    if(ok)good++;
    select.disabled=true;row.classList.add(ok?'correct':'wrong');
   });
   const all=good===selects.length;
   setFeedback(all,all?'Toutes les associations sont justes.':`${good} association(s) sur ${selects.length} juste(s).`,q.explanation);
   return all;
  }};
 }
 const inputs=q.options.map((text,j)=>{
  const label=document.createElement('label');label.className='quiz-option';
  const radio=document.createElement('input');radio.type='radio';radio.name=`question-${i}`;radio.value=String(j);
  const span=document.createElement('span');span.textContent=kind==='true_false'?text:`${'ABCD'[j]}. ${text}`;
  label.append(radio,span);node.append(label);
  return {label,radio};
 });
 node.append(feedback);
 return {node,scored:true,answered:()=>inputs.some(({radio})=>radio.checked),value:()=>{const picked=inputs.findIndex(({radio})=>radio.checked);return picked===-1?null:picked;},check:()=>{
  const picked=inputs.findIndex(({radio})=>radio.checked);
  inputs.forEach(({label,radio},j)=>{radio.disabled=true;if(j===q.correct)label.classList.add('correct');else if(j===picked)label.classList.add('wrong');});
  const right=picked===q.correct;
  setFeedback(right,picked===-1?'Pas de réponse.':right?'Bonne réponse.':'Ce n’est pas la bonne réponse.',q.explanation);
  return right;
 }};
}
function correctQuiz(rows,quizId){
 const answers=rows.map(row=>row.value());
 let score=0,scored=0;
 rows.forEach(({check})=>{
  const result=check();
  if(result===null)return;
  scored++;if(result)score++;
 });
 $('#result').textContent=`Score : ${score} / ${scored}`;
 const pct=scored?Math.round(score/scored*100):0;
 const summary=document.createElement('div');summary.className='quiz-summary';summary.setAttribute('role','status');
 const num=document.createElement('div');num.className='quiz-score-num';num.textContent=String(score);
 const outOf=document.createElement('small');outOf.textContent=`/ ${scored}`;num.append(outOf);
 const text=document.createElement('div');text.className='quiz-summary-text';
 const title=document.createElement('strong');
 title.textContent=pct===100?'Parfait, sans faute !':pct>=60?'Bien joué : revoyez les erreurs.':'Pas de souci : relisez le cours et recommencez.';
 const summaryBar=document.createElement('div');summaryBar.className='quiz-bar';const summaryFill=document.createElement('span');summaryFill.style.width=`${pct}%`;summaryBar.append(summaryFill);
 text.append(title,summaryBar);summary.append(num,text);
 if(quizId){
  const exportButton=document.createElement('button');exportButton.type='button';exportButton.className='quiz-export';exportButton.textContent='Exporter en PDF';
  exportButton.onclick=()=>exportQuizPdf(quizId,answers,exportButton);
  text.append(exportButton);
 }
 $('#fields').prepend(summary);summary.scrollIntoView({block:'nearest'});
 if(quizId)api('quiz_score',{method:'POST',body:new URLSearchParams({quiz_id:String(quizId),answers:JSON.stringify(answers)})}).then(loadStats).catch(e=>notice(e.message));
 const progressLabel=document.querySelector('#fields .quiz-progress-text');if(progressLabel)progressLabel.textContent='Quiz corrigé';
 $('#fields').onchange=null;
 const action=$('#action');action.textContent='Nouveau quiz';action.onclick=openQuizHome;
}
/* Export PDF : le serveur recalcule la correction à partir du quiz enregistré ; le navigateur n’envoie que les choix. */
async function exportQuizPdf(quizId,answers,button){
 const label=button.textContent;
 button.disabled=true;button.textContent='Préparation du PDF…';
 try{
  const response=await fetch('api.php?action=quiz_pdf',{method:'POST',headers:{'X-CSRF-Token':csrf},body:new URLSearchParams({quiz_id:String(quizId),answers:JSON.stringify(answers)})});
  if(response.status===401){location.href='login.php';return;}
  if(!response.ok){let message='Export impossible. Réessayez.';try{message=(await response.json()).error||message;}catch{}throw new Error(message);}
  const url=URL.createObjectURL(await response.blob());
  const link=document.createElement('a');link.href=url;link.download=`quiz-reponses-${quizId}.pdf`;
  document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),2000);
  button.textContent='PDF téléchargé';
  setTimeout(()=>{button.textContent=label;button.disabled=false;},2500);
 }catch(e){$('#result').textContent=e.message;button.textContent=label;button.disabled=false;}
}
async function loadSavedQuizzes(container){
 try{
  const data=await api('quizzes');
  if(!data.quizzes.length)return;
  const heading=document.createElement('p');heading.className='quiz-label';heading.textContent='Quiz déjà générés';
  const list=document.createElement('ul');list.className='quiz-saved';
  data.quizzes.forEach(item=>{
   const li=document.createElement('li');const button=document.createElement('button');
   button.type='button';button.className='textbtn';button.textContent=`${item.title} · ${item.question_count} questions`;
   button.onclick=()=>openSavedQuiz(item.id);li.append(button);list.append(li);
  });
  container.append(heading,list);
 }catch(e){notice(e.message);}
}
async function openSavedQuiz(id){
 $('#result').textContent='Ouverture du quiz…';
 try{const data=await api(`quiz&id=${encodeURIComponent(id)}`);showQuiz(data.quiz);}
 catch(e){$('#result').textContent=e.message;}
}
async function loadQuizCount(){
 try{const data=await api('quizzes');$('#quizcount').textContent=data.quizzes.length;}catch{}
}
$('.close').onclick=()=>$('#modal').close();
$('#modal').onclick=e=>{if(e.target===$('#modal'))$('#modal').close();};
document.querySelectorAll('[data-nav]').forEach(button=>button.onclick=()=>{
 document.querySelectorAll('[data-nav]').forEach(n=>n.classList.toggle('active',n===button));$('#breadcrumb').textContent=button.dataset.nav;
 if(button.dataset.nav==='Mes cours'){$('#courses').scrollIntoView({behavior:'smooth',block:'center'});$('#search').focus();}else window.scrollTo({top:0,behavior:'smooth'});
});
loadCourses().catch(e=>notice(e.message));
loadQuizCount();
async function loadStats(){
 try{const data=await api('stats');$('#avgscore').textContent=data.average===null?'—':`${data.average} %`;$('#avglabel').textContent=data.attempts?`Score moyen (${data.attempts} quiz corrigé${data.attempts>1?'s':''})`:'Aucun quiz corrigé';}catch{}
}
loadStats();
