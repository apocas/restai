<?php

/**
 * RESTai PHP demo — full RAG lifecycle.
 *
 *   discover models  →  ensure a team  →  create project  →  ingest
 *                    →  ask (grounded answer)  →  search  →  cleanup
 *
 * Config via env (all optional; defaults target local dev):
 *   RESTAI_URL       default http://localhost:9000
 *   RESTAI_API_KEY   Bearer key (preferred). If unset, falls back to Basic auth.
 *   RESTAI_USER      default admin
 *   RESTAI_PASSWORD  default admin
 *
 *   php main.php
 *
 * Full API reference: <your-restai>/docs (Swagger).
 */

require_once('Project.php');

$url    = getenv('RESTAI_URL') ?: 'http://localhost:9000';
$apikey = getenv('RESTAI_API_KEY') ?: null;
$user   = getenv('RESTAI_USER') ?: 'admin';
$pass   = getenv('RESTAI_PASSWORD') ?: 'admin';

$modem = $apikey
  ? new Modem($url, $apikey)
  : new Modem($url, null, $user, $pass);

echo "→ RESTai at $url\n";

// 1. Discover models. RESTai seeds none — you configure them in /admin.
$llms = $modem->get('/llms');
$embeddings = $modem->get('/embeddings');
if (empty($llms) || empty($embeddings)) {
  fwrite(STDERR, "Configure at least one LLM and one embeddings model in /admin first.\n");
  exit(1);
}
$llm = $llms[0]['name'];
$emb = $embeddings[0]['name'];
echo "→ using LLM '$llm' and embeddings '$emb'\n";

// 2. Ensure a team that can use those models (projects belong to a team).
$teams = $modem->get('/teams')['teams'] ?? [];
$team = null;
foreach ($teams as $t) {
  if ($t['name'] === 'examples') { $team = $t; break; }
}
if ($team === null) {
  // Creating with llms/embeddings name lists grants access in one shot.
  $team = $modem->post('/teams', [
    'name' => 'examples', 'description' => 'RESTai examples',
    'llms' => [$llm], 'embeddings' => [$emb],
  ]);
}
$teamId = $team['id'];

// 3. Create the RAG project (or reuse it if a previous run left it behind).
$proj = Project::find($modem, 'examples_php') ?? Project::create($modem, 'examples_php', 'rag', $teamId, [
  'llm' => $llm,
  'embeddings' => $emb,
  'vectorstore' => 'chroma',
  'human_name' => 'PHP Example',
]);
echo "→ project id {$proj->id}\n";

// 4. Ingest some knowledge.
$proj->ingestText('The meaning of life, the universe, and everything is 42.', 'meaning-of-life');
echo "→ ingested text\n";

// 5. Ask a grounded question. k/score are optional per-request retrieval knobs.
$reply = $proj->chat('What is the meaning of life?', ['k' => 2, 'score' => 0.0]);
echo "Q: What is the meaning of life?\n";
echo "A: {$reply['answer']}\n";
echo '   (' . count($reply['sources'] ?? []) . " source chunk(s))\n";

// 6. Semantic search (no LLM call).
echo "→ search 'meaning of life':\n";
foreach ($proj->search('meaning of life', ['k' => 2]) as $hit) {
  printf("   score=%.3f source=%s\n", $hit['score'], $hit['source']);
}

// 7. Edit a property (here: swap the LLM — must already be granted to the team).
$proj->edit(['human_description' => 'Updated by main.php']);
echo "→ edited project\n";

// 8. Cleanup (set KEEP=1 to leave it for inspection in /admin).
if (!in_array(getenv('KEEP'), ['1', 'true', 'yes'], true)) {
  $proj->delete();
  echo "→ deleted project {$proj->id}\n";
}
