import * as Blockly from "blockly";

// Module-level store for project names — updated via setProjectNames(),
// read dynamically each time the "Call Project" dropdown opens.
let _projectNames = [];

export function setProjectNames(names) {
  _projectNames = names || [];
}

function projectDropdownGenerator() {
  if (_projectNames.length > 0) {
    return _projectNames.map((n) => [n, n]);
  }
  return [["(no projects)", ""]];
}

export function registerCustomBlocks() {
  // --- restai_get_input ---
  Blockly.Blocks["restai_get_input"] = {
    init: function () {
      this.appendDummyInput().appendField("Get Input");
      this.setOutput(true, "String");
      this.setColour(210);
      this.setTooltip("Returns the input text (the question sent to this project)");
    },
  };

  // --- restai_set_output ---
  Blockly.Blocks["restai_set_output"] = {
    init: function () {
      this.appendValueInput("VALUE")
        .setCheck("String")
        .appendField("Set Output");
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(210);
      this.setTooltip("Sets the output text (the answer returned by this project)");
    },
  };

  // --- restai_call_project ---
  Blockly.Blocks["restai_call_project"] = {
    init: function () {
      this.appendValueInput("TEXT")
        .setCheck("String")
        .appendField("Call Project")
        .appendField(new Blockly.FieldDropdown(projectDropdownGenerator), "PROJECT_NAME");
      this.setOutput(true, "String");
      this.setColour(210);
      this.setTooltip(
        "Calls another RESTai project with text input and returns its answer"
      );
    },
  };

  // --- restai_log ---
  Blockly.Blocks["restai_log"] = {
    init: function () {
      this.appendValueInput("TEXT").setCheck("String").appendField("Log");
      this.setPreviousStatement(true, null);
      this.setNextStatement(true, null);
      this.setColour(210);
      this.setTooltip("Logs a debug message");
    },
  };

  // --- text_contains ---
  Blockly.Blocks["text_contains"] = {
    init: function () {
      this.appendValueInput("VALUE")
        .setCheck("String")
        .appendField("text");
      this.appendValueInput("FIND")
        .setCheck("String")
        .appendField("contains");
      this.setOutput(true, "Boolean");
      this.setColour(160);
      this.setTooltip("Returns true if the text contains the given substring");
    },
  };
}
