using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;

// This probe uses the vendor's normal licence check. It never changes licence
// data, starts a trial, suppresses protection, or treats a failed check as success.
internal static class ProbeTflexSession
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetDllDirectory(string path);

    private static bool SetOption(object target, string name, object value)
    {
        Type type = target.GetType();
        PropertyInfo property = type.GetProperty(name);
        if (property != null && property.CanWrite)
        {
            property.SetValue(target, value, null);
            return true;
        }
        FieldInfo field = type.GetField(name);
        if (field != null)
        {
            field.SetValue(target, value);
            return true;
        }
        return false;
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string program = Path.GetFullPath(args[0]);
            string output = Path.GetFullPath(args[1]);
            Directory.CreateDirectory(output);
            Environment.CurrentDirectory = program;
            Environment.SetEnvironmentVariable("PATH", program + ";" + Environment.GetEnvironmentVariable("PATH"));
            if (!SetDllDirectory(program)) throw new InvalidOperationException("Cannot select the vendor DLL directory.");
            AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs request)
            {
                string path = Path.Combine(program, new AssemblyName(request.Name).Name + ".dll");
                return File.Exists(path) ? Assembly.LoadFrom(path) : null;
            };

            Console.WriteLine("STAGE=LOAD_OFFICIAL_API");
            Assembly api = Assembly.LoadFrom(Path.Combine(program, "TFlexAPI.dll"));
            Type application = api.GetType("TFlex.Application", true);
            Type setupType = api.GetType("TFlex.ApplicationSessionSetup", true);
            File.WriteAllLines(Path.Combine(output, "api-public-signatures.txt"),
                application.GetMethods(BindingFlags.Public | BindingFlags.Static)
                    .Select(method => method.ToString())
                    .Concat(setupType.GetProperties().Select(property => "SETUP " + property.ToString()))
                    .Concat(setupType.GetFields().Select(field => "SETUP " + field.ToString())));
            foreach (string name in new[] { "TFlexAPI.xml", "TFlexAPI3D.xml" })
            {
                string source = Path.Combine(program, name);
                if (!File.Exists(source)) continue;
                var xml = new System.Xml.XmlDocument();
                xml.Load(source);
                var members = xml.SelectNodes("//member");
                using (var writer = new StreamWriter(Path.Combine(output, name + ".selected.txt")))
                {
                    foreach (System.Xml.XmlNode member in members)
                    {
                        string id = member.Attributes["name"].Value;
                        if (id.Contains("InitSession") || id.Contains("NewDocument") ||
                            id.Contains("CreateNew") || id.Contains("ImportFromSTEP") ||
                            id.Contains("ImportFrom3dCommon") || id.Contains("Document.SaveAs"))
                            writer.WriteLine(id + " " + member.InnerText.Trim());
                    }
                }
            }

            object setup = Activator.CreateInstance(setupType);
            if (!SetOption(setup, "ReadOnly", false) || !SetOption(setup, "Enable3D", true))
                throw new InvalidOperationException("Required writable 3D session options are missing.");
            SetOption(setup, "PromptToSaveModifiedDocuments", false);
            // This option controls licence UI, not the licence check itself.
            // An unattended runner must fail instead of waiting on a modal form.
            SetOption(setup, "PromptToCheckLicense", false);
            Console.WriteLine("STAGE=CHECK_NORMAL_WRITABLE_3D_LICENCE");
            MethodInfo init = application.GetMethod("InitSession", new[] { setupType });
            bool initialized = (bool)init.Invoke(null, new[] { setup });
            Console.WriteLine("SESSION_INITIALIZED=" + initialized);
            if (!initialized) return 20;
            try
            {
                PropertyInfo evaluation = application.GetProperty("IsEvaluationVersion");
                if (evaluation != null) Console.WriteLine("EVALUATION=" + evaluation.GetValue(null, null));
                Console.WriteLine("WRITABLE_SESSION_AVAILABLE=true");
                // Session availability is a prerequisite, not an exported model.
                // A later import/save/reopen gate must verify an actual .grb.
                return 0;
            }
            finally { application.GetMethod("ExitSession", Type.EmptyTypes).Invoke(null, null); }
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.ToString());
            return 21;
        }
    }
}
