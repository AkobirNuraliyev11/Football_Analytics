import {defineConfig} from 'vite';
export default defineConfig({base:'/dashboard/',server:{host:'127.0.0.1',proxy:{'/jobs':'http://127.0.0.1:8000','/session':'http://127.0.0.1:8000'}}});
