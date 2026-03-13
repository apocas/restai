import {
  Container
} from "@mui/material";

import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { CopyBlock, monoBlue } from "react-code-blocks";


export default function APIPython({ project }) {
  const replaceVars = (code) => {
    code = code.replaceAll('<URL>', window.location.protocol + "//" + window.location.host);
    code = code.replaceAll('<PROJECT>', project.name);
    code = code.replaceAll('<QUESTION>', project.default_prompt || 'Who was born first? Chicken or egg?');
    return code;
  }

  const phpquestioncode = () => {
    return replaceVars(`<?php
  
  $apiKey = 'YOUR_API_KEY';
  
  $data = [
  'question' => '<QUESTION>',
  ];
  
  $ch = curl_init('<URL>/projects/<PROJECT>/question');
  
  curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
  curl_setopt($ch, CURLOPT_POST, true);
  curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
  curl_setopt($ch, CURLOPT_HTTPHEADER, [
  'Content-Type: application/json',
  'Authorization: Bearer ' . $apiKey,
  ]);
  
  $response = curl_exec($ch);
  
  if (curl_errno($ch)) {
  echo 'Error:' . curl_error($ch);
  } else {
  $responseData = json_decode($response, true);
  print_r($responseData);
  }
  
  curl_close($ch);`);
  }

  const phpchatcode = () => {
    return replaceVars(`<?php
  
  $apiKey = 'YOUR_API_KEY';
  
  $data = [
  'question' => '<QUESTION>',
  //'id' => 'XXXXXXXXXXX' //First iteration should not contain ID it will start a new chat history. Use the ID returned in the first response to continue the chat. 
  ];
  
  $ch = curl_init('<URL>/projects/<PROJECT>/chat');
  
  curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
  curl_setopt($ch, CURLOPT_POST, true);
  curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
  curl_setopt($ch, CURLOPT_HTTPHEADER, [
  'Content-Type: application/json',
  'Authorization: Bearer ' . $apiKey,
  ]);
  
  $response = curl_exec($ch);
  
  if (curl_errno($ch)) {
  echo 'Error:' . curl_error($ch);
  } else {
  $responseData = json_decode($response, true);
  print_r($responseData);
  }
  
  curl_close($ch);`);
  }

  return (
    <Container maxWidth="100%">
      <Accordion>
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          aria-controls="panel1-content"
          id="panel1-header"
        >
          PHP Question (stateless) Usage
        </AccordionSummary>
        <AccordionDetails>
          <CopyBlock
            text={phpquestioncode()}
            language="php"
            theme={monoBlue}
            $codeBlock
          />
        </AccordionDetails>
      </Accordion>
      <Accordion>
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          aria-controls="panel1-content"
          id="panel1-header"
        >
          PHP Chat (stateful) Usage
        </AccordionSummary>
        <AccordionDetails>
          <CopyBlock
            text={phpchatcode()}
            language="php"
            theme={monoBlue}
            $codeBlock
          />
        </AccordionDetails>
      </Accordion>
    </Container>
  );
}