<?php

require_once('Modem.php');

/**
 * A RESTai project, addressed by its integer id.
 *
 * Note the two big changes from older RESTai: projects are referenced by
 * **id** (not name) in every path, and chatting goes through /chat (the old
 * /question is deprecated). The reply shape is:
 *   ["answer" => "...", "sources" => [...], "type" => "...", "id" => "..."]
 */
class Project {
  protected $modem;
  public $id;

  public function __construct(Modem $modem, int $id) {
    $this->modem = $modem;
    $this->id = $id;
  }

  /** Create a project and return a Project bound to its new id.
   *  $opts may include: llm, embeddings, vectorstore, human_name, human_description. */
  public static function create(Modem $modem, string $name, string $type, int $teamId, array $opts = []): Project {
    $body = array_merge($opts, ['name' => $name, 'type' => $type, 'team_id' => $teamId]);
    $out = $modem->post('/projects', $body);
    return new Project($modem, $out['project']);
  }

  /** Find an existing project by name, or null. */
  public static function find(Modem $modem, string $name): ?Project {
    $page = $modem->get('/projects?start=0&end=1000');
    foreach (($page['projects'] ?? []) as $p) {
      if ($p['name'] === $name) {
        return new Project($modem, $p['id']);
      }
    }
    return null;
  }

  /** Send a chat turn. Returns the full reply array; reuse $chatId to keep context. */
  public function chat(string $question, array $opts = []): array {
    $body = array_merge($opts, ['question' => $question]);
    return $this->modem->post("/projects/{$this->id}/chat", $body);
  }

  /** Convenience: just the answer text. */
  public function ask(string $question, array $opts = []): string {
    return $this->chat($question, $opts)['answer'];
  }

  public function ingestText(string $text, string $source, array $opts = []): array {
    $body = array_merge($opts, ['text' => $text, 'source' => $source]);
    return $this->modem->post("/projects/{$this->id}/embeddings/ingest/text", $body);
  }

  public function ingestUrl(string $url, array $opts = []): array {
    $body = array_merge($opts, ['url' => $url]);
    return $this->modem->post("/projects/{$this->id}/embeddings/ingest/url", $body);
  }

  /** Semantic search over the knowledge base. Returns the matches array. */
  public function search(string $text, array $opts = []): array {
    $body = array_merge($opts, ['text' => $text]);
    $out = $this->modem->post("/projects/{$this->id}/embeddings/search", $body);
    return $out['embeddings'] ?? [];
  }

  public function edit(array $patch): array {
    return $this->modem->patch("/projects/{$this->id}", $patch);
  }

  public function delete(): array {
    return $this->modem->delete("/projects/{$this->id}");
  }
}
