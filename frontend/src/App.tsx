import { useEffect } from 'react';
import './i18n';
import { Layout } from './components/Layout/Layout';

function App() {
  useEffect(() => {
    const dark = localStorage.getItem('yuqing_dark_mode');
    if (dark === '1') {
      document.documentElement.classList.add('dark');
    }
    const fs = localStorage.getItem('yuqing_font_scale');
    if (fs) {
      document.documentElement.style.setProperty('--font-scale', fs);
    }
    const is_ = localStorage.getItem('yuqing_icon_scale');
    if (is_) {
      document.documentElement.style.setProperty('--icon-scale', is_);
    }
  }, []);

  return <Layout />;
}

export default App;
