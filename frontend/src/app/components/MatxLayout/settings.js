import { themes } from '../MatxTheme/initThemes';
import layout1Settings from './Layout1/Layout1Settings';


export const MatxLayoutSettings = {
  activeLayout: 'layout1',
  activeTheme: 'blue',
  perfectScrollbar: false,

  themes: themes,
  layout1Settings,

  footer: {
    show: true,
    fixed: false,
    theme: 'slateDark1'
  }
};
