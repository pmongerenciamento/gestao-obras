import { getFullDateExtenso, getGreeting } from "@/lib/date/greeting";

interface GreetingProps {
  name: string;
}

export function Greeting({ name }: GreetingProps) {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-black">
        {getGreeting()}, {name}
      </h1>
      <p className="text-sm text-black/50">{getFullDateExtenso()}</p>
    </div>
  );
}
