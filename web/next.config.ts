import type {NextConfig} from "next";
const api=process.env.SCRUBMETA_API_URL||"http://127.0.0.1:8770";
const config:NextConfig={async rewrites(){return [{source:"/backend/:path*",destination:`${api}/:path*`}]}};
export default config;