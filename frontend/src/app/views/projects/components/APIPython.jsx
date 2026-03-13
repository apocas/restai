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

  const pythonquestioncode = () => {
    return replaceVars(`import requests

api_key = 'YOUR_API_KEY'

data = {
    'question': '<QUESTION>',
}

headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {api_key}',
}

response = requests.post('<URL>/projects/<PROJECT>/question', json=data, headers=headers)

if response.status_code != 200:
    print('Error:', response.status_code, response.text)
else:
    response_data = response.json()
    print(response_data)`);
  }

  const pythonchatcode = () => {
    return replaceVars(`import requests

api_key = 'YOUR_API_KEY'

data = {
    'question': '<QUESTION>',
      #'id' => 'XXXXXXXXXXX' //First iteration should not contain ID it will start a new chat history. Use the ID returned in the first response to continue the chat.
}

headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {api_key}',
}

response = requests.post('<URL>/projects/<PROJECT>/chat', json=data, headers=headers)

if response.status_code != 200:
    print('Error:', response.status_code, response.text)
else:
    response_data = response.json()
    print(response_data)`);
  }

  return (
    <Container maxWidth="100%">
      <Accordion>
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          aria-controls="panel1-content"
          id="panel1-header"
        >
          Python Question (stateless) Usage
        </AccordionSummary>
        <AccordionDetails>
          <CopyBlock
            text={pythonquestioncode()}
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
          Python Chat (stateful) Usage
        </AccordionSummary>
        <AccordionDetails>
          <CopyBlock
            text={pythonchatcode()}
            language="php"
            theme={monoBlue}
            $codeBlock
          />
        </AccordionDetails>
      </Accordion>
    </Container>
  );
}