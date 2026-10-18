import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useSession } from './context';
import { ApiError } from './api';
import { Empty, ErrorState, Loading } from './components';
import { AuthPage, Landing, Legal } from './Public';
import { Shell } from './Shell';
import { Dashboard } from './Dashboard';
import { EventDetail, Events } from './Events';
import { AlertDetail, Alerts } from './Alerts';
import { SourceEditor, Sources } from './Sources';
import { ParserLab, RuleEditor, Rules } from './Rules';
import { AuditTrail, Notifications, Profile, Reports, Security } from './Account';
import { Settings } from './Settings';

function Protected() { const session = useSession(); if (session.isPending) return <Loading />; if (session.error) return session.error instanceof ApiError && session.error.status === 401 ? <Navigate to="/login" replace /> : <ErrorState error={session.error} retry={() => session.refetch()} />; return <AuthProvider user={session.data}><Shell /></AuthProvider>; }
export function App() { return <Routes><Route path="/" element={<Landing />} /><Route path="/login" element={<AuthPage mode="login" />} /><Route path="/forgot-password" element={<AuthPage mode="forgot" />} /><Route path="/reset-password" element={<AuthPage mode="reset" />} /><Route path="/privacy" element={<Legal privacy />} /><Route path="/terms" element={<Legal privacy={false} />} /><Route element={<Protected />}><Route path="/dashboard" element={<Dashboard />} /><Route path="/analytics" element={<Dashboard analytics />} /><Route path="/events" element={<Events />} /><Route path="/events/:id" element={<EventDetail />} /><Route path="/alerts" element={<Alerts />} /><Route path="/alerts/:id" element={<AlertDetail />} /><Route path="/investigations" element={<Alerts investigations />} /><Route path="/sources" element={<Sources />} /><Route path="/sources/new" element={<SourceEditor />} /><Route path="/sources/:id/edit" element={<SourceEditor />} /><Route path="/parsers" element={<ParserLab />} /><Route path="/rules" element={<Rules />} /><Route path="/rules/new" element={<RuleEditor />} /><Route path="/rules/:id/edit" element={<RuleEditor />} /><Route path="/reports" element={<Reports />} /><Route path="/notifications" element={<Notifications />} /><Route path="/profile" element={<Profile />} /><Route path="/security" element={<Security />} /><Route path="/audit" element={<AuditTrail />} /><Route path="/settings" element={<Settings />} /></Route><Route path="*" element={<Empty title="Page not found" description="Use your browser’s back button or open /dashboard to return to your workspace." />} /></Routes>; }
