<?php

require_once('Modem.php');

class Project {
  protected $name;
  protected $modem;
  protected $llm;
  protected $embeddings;
  protected $type;

  public function __construct($name, $type, $url, $apikey) {
    $this->name = $name;
    $this->type = $type;
    $this->modem = new Modem($url, $apikey);
  }

  public function create($opts) {
    $opts['name'] = $this->name;
    $opts['type'] = $this->type;
    return $this->modem->execute('POST', '/projects', $opts);
  }

  public function delete() {
    return $this->modem->execute('DELETE', '/projects/' . $this->name);
  }

  //https://ai.ptisp.systems/docs#/default/ingest_text_projects__projectName__embeddings_ingest_text_post
  public function ingestText($text, $source, $opts = []) {
    $opts['text'] = $text;
    $opts['source'] = $source;
    return $this->modem->execute('POST', '/projects/' . $this->name . '/embeddings/ingest/text', $opts);
  }

  public function edit($opts) {
    $output = $this->modem->execute('PATCH', '/projects/' . $this->name, $opts);
    if (isset($opts['name'])) {
      $this->name = $opts['name'];
    }
    return $output;
  }

  //https://ai.ptisp.systems/docs#/default/question_query_projects__projectName__question_post
  public function question($question, $opts = []) {
    $opts['question'] = $question;
    return $this->modem->execute('POST', '/projects/' . $this->name . '/question', $opts);
  }

  public function search($text, $opts = []) {
    $opts['text'] = $text;
    return $this->modem->execute('POST', '/projects/' . $this->name . '/embeddings/search', $opts);
  }
}