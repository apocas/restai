<?php

require_once('Project.php');

//project name, type, url, username, password
$proj = new Project('phptest', 'rag', 'http://restai.local', 'username', 'password');

https://ai.ptisp.systems/docs#/default/create_project_projects_post
$output = $proj->create(array("llm" => "openai_gpt4_turbo", "embeddings" => "all-mpnet-base-v2", "vectorstore" => "redis"));
print_r($output["response"]);

//https://ai.ptisp.systems/docs#/default/ingest_text_projects__projectName__embeddings_ingest_text_post
$output = $proj->ingestText("The meaning of life is 42." , "meaingoflife");
print_r($output["response"]);

//k, score and system are optional. If not provided they will be set to project defined values.
//https://ai.ptisp.systems/docs#/default/question_query_projects__projectName__question_post
$output = $proj->question("What is the meaning of life?", array("k" => 2, "score" => 0.4, "system" => "Always add 'beep boop' to the end of your questions."));
print_r($output["response"]);

//https://ai.ptisp.systems/docs#/default/search_projects__projectName__embeddings_search_post
$output = $proj->search("meaning of life");
print_r($output["response"]);

//https://ai.ptisp.systems/docs#/default/edit_project_projects__projectName__patch
$output = $proj->edit(array("llm" => "openai_gpt4"));
print_r($output["response"]);

$output = $proj->delete();
print_r($output["response"]);