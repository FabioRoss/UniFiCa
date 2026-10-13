import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import UpdateBar from "./components/UpdateBar";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";
import { ConfigProvider } from "./lib/app";
import Feed from "./pages/Feed";
import ItemPage from "./pages/ItemPage";
import Exams from "./pages/Exams";
import Notifications from "./pages/Notifications";
import Links from "./pages/Links";
import Info from "./pages/Info";
import NotFound from "./pages/NotFound";

// The admin panel is its own chunk: visitors never download it
const AdminApp = lazy(() => import("./admin/AdminApp"));

export default function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <ErrorBoundary>
          <Routes>
            <Route path="/admin/*" element={<Suspense fallback={<Loading />}><AdminApp /></Suspense>} />
            <Route element={<Layout />}>
              <Route index element={<Feed />} />
              <Route path="n/:id" element={<ItemPage />} />
              <Route path="esami" element={<Exams />} />
              <Route path="notifiche" element={<Notifications />} />
              <Route path="link" element={<Links />} />
              <Route path="info" element={<Info />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </ErrorBoundary>
        <UpdateBar />
      </BrowserRouter>
    </ConfigProvider>
  );
}
