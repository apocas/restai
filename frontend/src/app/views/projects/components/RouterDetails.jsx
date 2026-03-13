import { useState } from "react";
import { Box, Button, Card, Divider, styled, Stack, Paper, IconButton } from "@mui/material";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { FlexBox } from "app/components/FlexBox";
import { FileUpload } from "@mui/icons-material";
import React from 'react';
import Tree from 'react-d3-tree';
import { toast } from 'react-toastify';


import DeleteIcon from '@mui/icons-material/Delete';
import { AddBox } from "@mui/icons-material";

import { Typography } from "@mui/material";
import CustomizedDialogEntrance from "./CustomizedDialogEntrance";


export default function RouterDetails({ project, projects }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [selectedProject, setSelectedProject] = useState(null);
  const [loading, setLoading] = useState(false);

  const onClose = () => {
    setSelectedProject(null);
  }

  const handleDeleteEntrance = (routeName) => {
    if (window.confirm("Delete " + routeName + "?")) {
      project.entrances = project.entrances.filter((entrance) => entrance.name !== routeName);
      saveEntrances();
    }
  }

  const saveEntrances = () => {
    if (!loading) {
      setLoading(true);
      var opts = {
        "entrances": project.entrances
      }

      fetch(url + "/projects/" + project.id, {
        method: 'PATCH',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
        body: JSON.stringify(opts),
      })
        .then(function (response) {
          if (!response.ok) {
            response.json().then(function (data) {
              toast.error(data.detail);
            });
            throw Error(response.statusText);
          } else {
            return response.json();
          }
        })
        .then(() => {
          setLoading(false);
          //window.location.href = "/admin/project/" + project.id;
        }).catch(err => {
          setLoading(false);
          toast.error(err.toString());
        });
    }
  }

  const orgChart = {
    name: project.name,
    children: [],
  };

  project.entrances.map((entrance) => {
    orgChart.children.push({
      name: entrance.name,
      attributes: {
        destination: entrance.destination,
      }
    });
  });

  const Item = styled(Paper)(({ theme }) => ({
    backgroundColor: '#fff',
    ...theme.typography.body2,
    padding: theme.spacing(1),
    textAlign: 'center',
    color: theme.palette.text.secondary,
    ...theme.applyStyles('dark', {
      backgroundColor: '#1A2027',
    }),
  }));

  return (
    <Card elevation={3}>
      <FlexBox>
        <FileUpload sx={{ ml: 2, mt: 2 }} />
        <H4 sx={{ p: 2 }}>
          Router Layout
        </H4>
        <Button variant="outlined" onClick={() => { setSelectedProject(project) }} startIcon={<AddBox fontSize="small" />} sx={{"height": "40px", "marginTop":"8px"}}> 
          New route
        </Button>
      </FlexBox>

      <Divider />

      <Box sx={{ height: "200px" }}>
        <Tree
          data={orgChart}
          orientation="vertical"
          zoom={0.80}
          translate={{ x: 500, y: 40 }}
          collapsible={false}
          separation={{ siblings: 1.5, nonSiblings: 1.5 }}
          onNodeClick={(node, evt) => {
            console.log('onNodeClick', node, evt);
          }}
          onNodeMouseOver={(node, evt) => {
            console.log('onNodeMouseOver', node, evt);

          }}
        />
      </Box>

      <Box sx={{ p: 2 }}>
        <Stack direction="row" spacing={2}>
          {project.entrances.map((entrance, index) => (
            <Item>
              <Box key={index} sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <Box>
                  <h4 sx={{ pt: 0, pb: 0 }}>
                    {entrance.name}
                  </h4>
                  <Divider sx={{ mt: 1, mb: 1 }} />
                  <Typography variant="body1" color="text.secondary">
                    Destination: {entrance.destination}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {entrance.description}
                  </Typography>
                  <Divider sx={{ mt: 1, mb: 1 }} />
                  <IconButton
                    aria-label="delete"
                    onClick={() => handleDeleteEntrance(entrance.name)}
                    size="small"
                  >
                    <DeleteIcon />
                  </IconButton>
                </Box>

              </Box>
            </Item>
          ))}
        </Stack>
      </Box>

      <CustomizedDialogEntrance project={selectedProject} projects={projects} saveEntrances={saveEntrances} onClose={onClose} />

    </Card>
  );
}

