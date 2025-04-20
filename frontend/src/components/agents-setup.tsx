import { useState } from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Trash, Plus, Edit, Download, Save, Loader2 } from 'lucide-react';
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogClose, DialogFooter } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useTeamsContext, Agent, Team } from '@/contexts/TeamsContext';

interface AgentsSetupProps {
  team: Team;
  getAvatarSrc: (user: string) => string;
  isCollapsed: boolean;
}

export function AgentsSetup({ team, getAvatarSrc, isCollapsed }: AgentsSetupProps) {
  const { addAgent, removeAgent, addRAGAgent, editAgent, saveTeam } = useTeamsContext();
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [hasTeamChanged, setHasTeamChanged] = useState<boolean>(false);
  const [isSavingTeam, setIsSavingTeam] = useState<boolean>(false);

  return (
    <div className="space-y-4">
      <div className="grid auto-rows-min gap-4 md:grid-cols-2 text-sm">
        <h2>{team.name}</h2>
        {hasTeamChanged && (
          <Button variant="destructive" onClick={async () => { 
            setIsSavingTeam(true);
            await saveTeam(team);
            setHasTeamChanged(false);
            setIsSavingTeam(false);
          }}>
            <Save /> Update
          </Button>
        )}
      </div>
      <div className="grid auto-rows-min gap-4 md:grid-cols-5">
        {team.agents.map((agent) => (
          <div key={agent.input_key} className={`rounded-xl bg-muted/50 shadow ${isCollapsed ? 'p-0 duration-300 animate-in fade-in-0 zoom-in-75 origin-bottom-right' : 'p-4'}`}>
            <div className="flex items-center space-x-2">
              <Avatar>
                <AvatarImage src={getAvatarSrc(agent.name)} />
                <AvatarFallback>{agent.icon}</AvatarFallback>
              </Avatar>
              <div>
                <p className="text-sm font-semibold">{agent.name}</p>
                {!isCollapsed && <p className="text-sm text-muted-foreground">{agent.type}</p>}
              </div>
            </div>
            {!isCollapsed && (
              <>
                <Separator className="my-2" />
                <div className="flex space-x-2">
                  <Button size="icon" variant="outline" onClick={() => { removeAgent(team.team_id, agent.input_key); setHasTeamChanged(true); }}>
                    <Trash />
                  </Button>
                  <Button size="icon" variant="outline" onClick={() => setEditingAgent(agent)}>
                    <Edit />
                  </Button>
                  <Button size="icon" variant="outline">
                    <Download />
                  </Button>
                </div>
              </>
            )}
          </div>
        ))}

        {!isCollapsed && (
          <div className="rounded-xl bg-muted/50 shadow p-4">
            <Dialog>
              <DialogTrigger asChild>
                <Button size="sm" variant="outline">
                  <Plus className="h-4 w-4" />
                  Add agent
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-[80vw] max-h-[100vh]">
                <DialogHeader>
                  <DialogTitle>Add agent</DialogTitle>
                  <DialogDescription>
                    Note: Always use unique name with no spaces. Always fill System message and Description.
                  </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="name" className="text-right">Name</Label>
                    <Input id="name" defaultValue="MyAgent1" className="col-span-3" />
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="description" className="text-right">Description</Label>
                    <Textarea id="description" className="col-span-3" placeholder="Describe the agent capabilities so the orchestrator can use it." />
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="system_message" className="text-right">System Message</Label>
                    <Textarea
                      id="system_message"
                      className="col-span-3 font-mono"
                      rows={10}
                      placeholder='In the system message use as last sentence: Reply "TERMINATE" in the end when everything is done.'
                    />
                  </div>
                </div>
                <DialogFooter className="sm:justify-start">
                  <DialogClose asChild>
                    <Button
                      type="button"
                      onClick={() => {
                        const name = (document.getElementById('name') as HTMLInputElement).value;
                        const description = (document.getElementById('description') as HTMLTextAreaElement).value;
                        const systemMessage = (document.getElementById('system_message') as HTMLTextAreaElement).value;
                        addAgent(team.team_id, name, description, systemMessage);
                        setHasTeamChanged(true);
                      }}
                      variant="default"
                    >
                      Save & Close
                    </Button>
                  </DialogClose>
                </DialogFooter>
              </DialogContent>
            </Dialog>
            <Separator className="my-4" />
            <Dialog>
              <DialogTrigger asChild>
                <Button size="sm" variant="outline">
                  <Plus className="h-4 w-4" />
                  Add RAG agent
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-[80vw] max-h-[100vh]">
                <DialogHeader>
                  <DialogTitle>Add RAG agent</DialogTitle>
                  <DialogDescription>
                    <strong>Name</strong> Always use unique name with no spaces. 
                    <br />
                    <strong>Description</strong> is important! - always include what information could be found in the file so the Orchestrator.
                    <br />
                    <strong>Index name</strong> is the name of the index where the files will be indexed.
                    <br />
                    Indexing can take a while depending on the file size and number of files. After you submit the indexing starts.
                    
                  </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="name" className="text-right">Name</Label>
                    <Input id="name" defaultValue="MyRAGAgent1" className="col-span-3" />
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="description" className="text-right">Description</Label>
                    <Textarea
                      id="description"
                      className="col-span-3"
                      defaultValue=""
                      placeholder="An agent that has access to internal index and can handle RAG tasks, call this agent if you are getting questions on your internal index namely about Contoso company Car policy."
                    />
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="index_name" className="text-right">Index</Label>
                    <Input id="index_name" className="col-span-3" defaultValue="" placeholder="<your-index-name>" />
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="file_upload" className="text-right">Knowledge File</Label>
                    <Input
                      id="file_upload"
                      type="file"
                      multiple
                      className="col-span-3"
                    />
                  </div>
                </div>
                <DialogFooter className="sm:justify-start">
                  <DialogClose asChild>
                    <Button
                      type="button"
                      onClick={() => {
                        const name = (document.getElementById('name') as HTMLInputElement).value;
                        const description = (document.getElementById('description') as HTMLTextAreaElement).value;
                        const indexName = (document.getElementById('index_name') as HTMLInputElement).value;
                        const files = (document.getElementById('file_upload') as HTMLInputElement).files;
                        addRAGAgent(team.team_id, name, description, indexName, files);
                        setHasTeamChanged(true);
                      }}
                      variant="default"
                    >
                      Store and Index
                    </Button>
                  </DialogClose>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        )}
      </div>

      {/* Edit Agent Dialog */}
      {editingAgent && (
        <Dialog open={true} onOpenChange={(open) => { if (!open) setEditingAgent(null); }}>
          <DialogContent className="max-w-[80vw] max-h-[100vh]">
            <DialogHeader>
              <DialogTitle>Edit agent</DialogTitle>
              <DialogDescription>
                Update the agent details below.
              </DialogDescription>
            </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid grid-cols-[150px_1fr] items-center gap-4">
                    <Label htmlFor="edit_name" className="text-right">Name</Label>
                    <Input id="edit_name" defaultValue={editingAgent.name} />
                </div>
                <div className="grid grid-cols-[150px_1fr] items-center gap-4">
                    <Label htmlFor="edit_description" className="text-right">Description</Label>
                    <Textarea id="edit_description" defaultValue={editingAgent.description} />
                </div>
                <div className="grid grid-cols-[150px_1fr] items-center gap-4">
                    <Label htmlFor="edit_system_message" className="text-right">System Message</Label>
                    <Textarea
                        id="edit_system_message"
                        defaultValue={`${editingAgent.system_message}`}
                        className="font-mono"
                        rows={10}
                    />
                </div>
            </div>
            <DialogFooter className="sm:justify-start">
              <DialogClose asChild>
                <Button
                  type="button"
                  onClick={() => {
                    const name = (document.getElementById('edit_name') as HTMLInputElement).value;
                    const description = (document.getElementById('edit_description') as HTMLTextAreaElement).value;
                    const systemMessage = (document.getElementById('edit_system_message') as HTMLTextAreaElement).value;
                    editAgent(team.team_id, editingAgent.input_key, name, description, systemMessage);
                    setEditingAgent(null);
                    setHasTeamChanged(true);
                  }}
                  variant="default"
                >
                  Save & Close
                </Button>
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      
      {/* Progress Dialog for saving team */}
      {isSavingTeam && (
        <Dialog open={true} onOpenChange={() => {}}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>Saving Team</DialogTitle>
            </DialogHeader>
            <div className="py-4">
            <Loader2 className="h-8 w-8 animate-spin" />  Team is being saved...
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}