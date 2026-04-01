import { Grid, TextField, MenuItem, Autocomplete, Divider } from "@mui/material";
import { Fragment } from "react";

export default function ProjectEditSecurity({ state, setState, handleChange, projects }) {
  return (
    <Grid container spacing={3}>
      <Grid item sm={6} xs={12}>
        <Autocomplete
          options={projects.filter((p) => p.name !== (state.name || '')).map((p) => p.name)}
          value={state.guard || null}
          onChange={(event, newValue) => {
            setState({ ...state, guard: newValue || "" });
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              fullWidth
              InputLabelProps={{ shrink: true }}
              label="Input Guard"
              variant="outlined"
              helperText="Project that evaluates user input before inference"
            />
          )}
        />
      </Grid>

      <Grid item sm={6} xs={12}>
        <Autocomplete
          options={projects.filter((p) => p.name !== (state.name || '')).map((p) => p.name)}
          value={state.options?.guard_output || null}
          onChange={(event, newValue) => {
            setState({ ...state, options: { ...state.options, guard_output: newValue || null } });
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              fullWidth
              InputLabelProps={{ shrink: true }}
              label="Output Guard"
              variant="outlined"
              helperText="Project that evaluates LLM responses after inference"
            />
          )}
        />
      </Grid>

      <Grid item sm={6} xs={12}>
        <TextField
          fullWidth
          InputLabelProps={{ shrink: true }}
          name="censorship"
          label="Censorship Message"
          variant="outlined"
          onChange={handleChange}
          value={state.censorship ?? ''}
          helperText="Message returned when a guard blocks a request"
        />
      </Grid>

      <Grid item sm={6} xs={12}>
        <TextField
          select
          fullWidth
          InputLabelProps={{ shrink: true }}
          label="Guard Mode"
          variant="outlined"
          value={state.options?.guard_mode || "block"}
          onChange={(e) => setState({ ...state, options: { ...state.options, guard_mode: e.target.value } })}
          helperText="Block stops the response, Warn flags but passes through"
        >
          <MenuItem value="block">Block</MenuItem>
          <MenuItem value="warn">Warn</MenuItem>
        </TextField>
      </Grid>

      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>

      <Grid item sm={6} xs={12}>
        <TextField
          fullWidth
          InputLabelProps={{ shrink: true }}
          name="rate_limit"
          label="Rate Limit (requests/min)"
          variant="outlined"
          type="number"
          onChange={handleChange}
          value={state.options?.rate_limit ?? ''}
          helperText="Maximum requests per minute. Leave empty for unlimited."
          inputProps={{ min: 1, max: 10000 }}
        />
      </Grid>
    </Grid>
  );
}
