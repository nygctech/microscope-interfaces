
# try to connect to ZEN blue dll through win32com, otherwise connect to dummy implementation for testing purposes
try:
    import win32com.client as microscopeConnection
    print ('Connected to microscope hardware')
except:
    import connectZenBlueDummy as microscopeConnection
    print ('Connected to simulation')

import time
import os.path

# create logger
import logging
# from .loadImageCzi import LoadImageCzi
from loadImageCzi import LoadImageCzi
log = logging.getLogger('microscopeAutomation connectZen Blue')

# import modules from project MicroscopeAutomation
try:
    from RS232 import Braintree
except:
    from RS232dummy import Braintree

# from .automationExceptions import AutomationError, HardwareError, AutofocusError, AutofocusObjectiveChangedError, AutofocusNotSetError, LoadNotDefinedError, ExperimentError
from automationExceptions import AutomationError, HardwareError, AutofocusError, AutofocusObjectiveChangedError, AutofocusNotSetError, LoadNotDefinedError, ExperimentError

############################################################################################
#
# Class to control Zeiss hardware through the Zeiss software Zen blue
# To use this class dll have to be exported.
#
############################################################################################

class connectMicroscope():
    '''
    Simmulation: Connect to Carl Zeiss ZEN blue Python API.
    
    To be able to use ZEN services in a COM environment, 
    the ZEN functionality must be registered as follows as administrator
    (you might have to update versions):
    pushd "C:\Windows\Microsoft.NET\Framework64\v4.0.30319"
    SET dll-1="C:\Program Files\Carl Zeiss\ZEN 2\ZEN 2 (blue edition)\Zeiss.Micro.Scripting.dll"
    regasm /u /codebase /tlb %dll-1%
    regasm /codebase /tlb %dll-1%
    
    SET dll-2="C:\Program Files\Carl Zeiss\ZEN 2\ZEN 2 (blue edition)\Zeiss.Micro.LM.Scripting.dll"
    
    regasm /u /codebase /tlb %dll-2%
    regasm /codebase /tlb %dll-2%
    popd
    '''
    def __init__(self):
        '''
        Connect to Carl Zeiss ZEN blue Python API
        '''
        # setup logging
        # Import the ZEN OAD Scripting into Python
        self.Zen = microscopeConnection.GetActiveObject("Zeiss.Micro.Scripting.ZenWrapperLM")
        
        # predefine internal settings
        self.zLoad = None
        self.zWork = None
        self.image = None
        
        # Save stored position. We will use this position to move the objective to this position before recalling this position.
        # If the stored position is close to the find_surface position, Definite Focus works much faster.
        self.DFObjective = None
        self.DFStoredFocus = None
        self.lastKnownFocusPosition = None
        self.set_autofocus_not_ready()
        
        log.info('Connected to ZEN')

##################################################################################################################
#
# Methods to save and load images
#
##################################################################################################################

    def save_image(self, fileName):
        '''save last acquired imageAICS in original file format using microscope software
        
        Input:
         file: file name and path for imageAICS save
        '''
        try:
            self.image.Save_2(fileName)
            log.info('save imageAICS to ' + fileName)
        except Exception as err:
            log.exception(err)
            raise HardwareError('Error in save_image to {}.'.format(fileName))

    def load_image(self, image, getMeta=False):
        '''Load image using aicsimage and return it a class imageAICS
        
        Input:
         image: image object of class imageAICS. Holds meta data at this moment, no image data.
         getMeta: if true, retrieve meta data from file. Default is False
         
        Output:
         image: image with data and meta data as imageAICS class
         

        '''

        rz = LoadImageCzi()
        image = rz.load_image(image, get_meta_data=True)
        log.info('loaded file ' + image.get_meta('aics_filePath'))
        return image


 
##################################################################################################################
#
# Methods to acquire images
#
##################################################################################################################

    def snap_image(self, experiment = None):
        '''Snap image with parameters defined in experiment.
        
        Input:
         experiment: string with name of experiment as defined within Microscope software
                      If None use actual experiment.
        Return:
         nosuccess: True when image was snapped
         
        Image object is stored in self.image.
        Acquires single image from experiment (e.g. single slice of stack)
        '''
        success = True
        log.info('snap image using experiment ', experiment)

        # if method switches objective the stored position for definite focus will be invalid.
        currentObjective = self.get_objective_name()
        
        try:
            # call ZEN API to set experiment
            if experiment is None:
                # use active experiment in software. Will fail if no experiment is set.
                expClass = self.Zen.Acquisition.Experiments.ActiveExperiment
            else:
                expClass = self.Zen.Acquisition.Experiments.GetByName(experiment)
            # check if experiment exists
            if expClass is not None and self.Zen.Acquisition.Experiments.Contains(expClass):
                self.image = self.Zen.Acquisition.AcquireImage_3(expClass)
            else:
                success = False
                print 'Could not find experiment: ', experiment
        except:
            raise HardwareError('Error in snap_image.')
            
        # set flag for definite focus if objective was changed
        if currentObjective != self.get_objective_name() or self.get_objective_name() == '':
            self.set_autofocus_not_ready()   
        return success

    def close_experiment (self, experiment = None):
        '''Closes experiment and forces reload.

        Input:
         experiment: string with name of experiment as defined within Microscope software.

        Output:
         None
        '''
        expClass = self.Zen.Acquisition.Experiments.GetByName(experiment)
        expClass.Close()

    def get_experiment_folder(self):
        '''Return path to user specific experiment file.
        
        Input:
         none
         
        Output:
         experiment_path: path to experiment file
        '''
        user_document_path = self.Zen.Application.Environment.GetFolderPath(self.Zen.ZenSpecialFolder.UserDocuments)
        return user_document_path
    
    def wait_for_experiment(self, experiment):
        '''Wait until experimentis active experiment.
        
        Input:
         experiment: string with name of experiment as defined within Microscope software.
         
        Output:
         None
        '''
        # if experiment name contains extension remove it
        target_experiment = os.path.splitext(experiment)[0]
        while True:
            active_experiment = os.path.splitext(self.Zen.Acquisition.Experiments.ActiveExperiment.name)[0]
            print (active_experiment)
            if target_experiment == active_experiment:
                break

    def wait_for_objective(self, target_objective):
        '''Wait until objective is in place.
        
        Input:
         target_objective: string with name of objective.
         
        Output:
         None
        '''
        while True:
            current_objective = self.get_objective_name()
#             print ('Current objective:  {}\nTarget objective: {}'.format(current_objective, target_objective))
            if current_objective == target_objective:
                break
       
    def execute_experiment(self, experiment = None):
        '''Execute experiments with parameters defined in experiment.
        
        Input:
         experiment: string with name of experiment as defined within Microscope software.
                      If None use actual experiment.
         
        Return:
         none
         
        Image object is stored in self.image
        Takes all images that are part of experiment (e.g. all slices)
        '''
        log.info('execute experiment to acquire image using experiment %s', experiment)

        # if method switches objective the stored position for definite focus will be invalid.
        currentObjective = self.get_objective_name()

        # stop live mode, otherwise the wrong objective might be used
        self.live_mode_stop()
        
        try:
        # call ZEN API to set experiment
            if experiment is None:
                # use active experiment in software. Will fail if no experiment is set.
                expClass = self.Zen.Acquisition.Experiments.ActiveExperiment
            else:
                expClass = self.Zen.Acquisition.Experiments.GetByName(experiment)
        except:
            raise HardwareError('Error in execute_experiment (get experiment).')


        try:
            # Reason for the duplicate try except block: One specific experiment - WellTile_10x
            # fails to execute the first time the execution function is called. Hence, it needs
            # a second call if the first one fails, and that seems to fix the bug.
            # Note - This is a temporary fix. There is something messed up with the oommunication object.
            # We will be looking into it further.
            # TODO - MICRND-741
            try:
                # check if experiment exists
                if expClass is not None and self.Zen.Acquisition.Experiments.Contains(expClass):
                    self.image = self.Zen.Acquisition.Execute(expClass)
                    if self.image is None:
                        raise ExperimentError('Zen.Acquisition.Execute() did not return image.')
                else:
                    raise ExperimentError('Could not find experiment "{}"'.format(experiment))
            except:
                if expClass is not None and self.Zen.Acquisition.Experiments.Contains(expClass):
                    self.image = self.Zen.Acquisition.Execute(expClass)
                    if self.image is None:
                        raise ExperimentError('Zen.Acquisition.Execute() did not return image.')
                else:
                    raise ExperimentError('Could not find experiment "{}"'.format(experiment))
        except:
            raise HardwareError
        # set flag for definite focus if objective was changed
        if currentObjective != self.get_objective_name() or self.get_objective_name() == '':
            self.set_autofocus_not_ready()   


    def live_mode_start(self, experiment = None):
        '''Start live mode of ZEN software.
        
        Input: 
         experiment: name of ZEN experiment (default = None)
         
        Output:
         liveImage: image of type ZenImage
        '''
        # if method switches objective the stored position for definite focus will be invalid.
        currentObjective = self.get_objective_name()

        try:
            if experiment:            
                # get experiment as type ZenExperiment by name
                expClass = self.Zen.Acquisition.Experiments.GetByName(experiment)
                # Reason for the duplicate try except block: One specific experiment - WellTile_10x
                # fails to enter live mode the first time the execution function is called. Hence, it needs
                # a second call if the first one fails, and that seems to fix the bug.
                # Note - This is a temporary fix. There is something messed up with the oommunication object.
                # We will be looking into it further.
                try:
                    imgLive = self.Zen.Acquisition.StartLive_2(expClass)
                except:
                    imgLive = self.Zen.Acquisition.StartLive_2(expClass)
            else:
                expClass = self.Zen.Acquisition.Experiments.ActiveExperiment
                imgLive = self.Zen.Acquisition.StartLive_2(expClass) 
        except:
            raise HardwareError('Error in live_mode_start.')

        # set flag for definite focus if objective was changed
        if currentObjective != self.get_objective_name() or self.get_objective_name() == '':
            self.set_autofocus_not_ready()   
            
        return imgLive

    def live_mode_stop(self, experiment = None):
        '''Stop live mode of ZEN software.
        
        Input: 
         experiment: name of ZEN experiment (default = None)
         
        Output:
         none
        '''
        try:
            if experiment:
                expClass = self.Zen.Acquisition.Experiments.GetByName(experiment)
                self.Zen.Acquisition.StopLive_2(expClass) 
            else:
                self.Zen.Acquisition.StopLive()   
        except:
            raise HardwareError('Error in live_mode_stop.')

##################################################################################################################
#
# Methods to interact with image display in ZEN
#
##################################################################################################################

    def show_image(self):
        '''Display last acquired image in ZEN software.
        
        Input:
         none
         
        Output:
         none
        '''
        try:
            if self.image is None:
                print 'No active image in ZEN Blue software'
            else:
                self.Zen.Application.Documents.Add(self.image)
        except:
            raise HardwareError('Error in show_image.')

    def remove_all(self):
        '''Remove all images from display within ZEN software.
        
        Input:
         none
         
        Output:
         none
        '''
        try:
            self.Zen.Application.Documents.RemoveAll(True)
        except:
            raise HardwareError('Error in remove_all.')

##################################################################################################################
#
# Methods to control motorized xy stage
#
##################################################################################################################
                      
    def get_stage_pos(self):
        '''Return current position of Microscope stage.
        
        Return:
         xPos, yPos: x and y position of stage in micrometer
        '''
        ## Get current stage position
        try:
            xPos = self.Zen.Devices.Stage.ActualPositionX
            yPos = self.Zen.Devices.Stage.ActualPositionY        
        except:
            raise HardwareError('Error in get_stage_pos.')
        return xPos, yPos  
    
#     def move_stage_to(self, xPos, yPos, zPos = None, load=True):
    def move_stage_to(self, xPos, yPos, test = False):

        '''Move stage to new position.
        
        Input:
         xPos, yPos: new stage position in micrometers.
         test: if True return travel path and do not move stage
         
        Return:
         xPos, yPos: x and y position of stage in micrometer after stage movement (if test = False)
         x_path, y_path: projected travel path (if test = True)
        '''
        if xPos is None or yPos is None:
            print ('No xPos')
            raise HardwareError('Position not defined in move_stage_to.')
        
        if test:
            x_current = self.Zen.Devices.Stage.ActualPositionX
            y_current = self.Zen.Devices.Stage.ActualPositionY 
            xy_path = [(x_current, y_current), (xPos, y_current), (xPos, yPos)]
            return xy_path
        
        try:
            self.Zen.Devices.Stage.TargetPositionX = xPos
            self.Zen.Devices.Stage.Apply()
            self.Zen.Devices.Stage.TargetPositionY = yPos
            self.Zen.Devices.Stage.Apply()
            # check new position
            xStage = self.Zen.Devices.Stage.ActualPositionX
            yStage = self.Zen.Devices.Stage.ActualPositionY 
        except:
            raise HardwareError('Error in move_stage_to.')
        return xStage, yStage

##################################################################################################################
#
# Methods to control focus including soft- and hardware autofocus
#
##################################################################################################################
    def set_autofocus_ready(self):
        '''Set flag that auto focus position for DF2 was stored and recall_focus should work.
        
        Input:
         none
         
        Output:
         none
        '''
        self.autofocusReady = True
        
    def set_autofocus_not_ready(self):
        '''Set flag that auto focus position for DF2 is not ready and recall_focus will not work.
        
        Input:
         none
         
        Output:
         none
        '''
        self.autofocusReady = False

    def get_autofocus_ready(self):
        '''Check if auto focus position for DF2 was stored and recall_focus should work.
        
        Input:
         none
         
        Output:
         ready: True if DF2 was initialized and recall_focus should work.
         
        Will raise exception if not ready.
        '''
        if not self.autofocusReady:
            raise AutofocusNotSetError(message = 'Definite Focus is not ready.')

        # do additional test to check if autofocus should work
        # a valid objective selected?
        if self.get_objective_name() == '' or self.DFObjective is None:
            self.set_autofocus_not_ready()
            raise AutofocusObjectiveChangedError(message='No objective selected.')
        # was objective changed since focus was stored?
        if self.DFObjective != self.get_objective_name():
            self.set_autofocus_not_ready()
            raise AutofocusObjectiveChangedError(message='Different objective was used to set focus position.')
        return True

    def set_last_known_focus_position(self, focusPostion):
        '''Stores focus position used for recovery if autofocus fails.
        
        Input:
         focusPostion: position in um to be used for autofocus recovery
         
        Output:
         none.
        '''
        self.lastKnownFocusPosition = focusPostion
        
    def get_last_known_focus_position(self):
        '''Retrieves focus position used for recovery if autofocus fails.
        
        Input:
         focusPostion: position in um to be used for autofocus recovery
         
        Output:
         none.
         
        Will raise AutofocusNotSetError exception if not defined
        '''
        if self.lastKnownFocusPosition is None:
            raise AutofocusNotSetError(message='Autofocus position not defined.')

        return self.lastKnownFocusPosition

        
    def recover_focus(self):
        '''Try to recover from autofocus failure.
        
        Input:
         none
         
        Output:
         none
        '''
        # Make sure valid objective is selected
        if self.get_objective_name() == '':
            self.set_autofocus_not_ready()
            raise AutofocusError(message='No objective selected.')
        
        # move focus to last know position
        self.move_focus_to(self.get_last_known_focus_position())
        self.store_focus()

                
    def find_autofocus(self, experiment):
        '''Focus with ZEN software autofocus.
        
        Input:
         experiment: string with name for experiment defined in ZEN
         
        Output:
         zPos: position of focus drive after autofocus
        '''
        try:
            # use definite focus to find bottom of plate
            self.Zen.Acquisition.FindSurface()
            experimentObj = self.Zen.Acquisition.Experiments.GetByName(experiment)
            # use FindAutofocus_2 instead of FindAutofocus because method with parameters overloads method without parameters
            self.Zen.Acquisition.FindAutofocus_2(experimentObj)
            zPos = self.get_focus_pos()
            
            # store offset to definite focus
            self.Zen.Acquisition.StoreFocus()
        except:
            raise HardwareError('Error in find_autofocus.')
        return zPos

    def find_surface(self):
        '''Find cover slip using Definite Focus 2.
        
        Input:
         none
         
        Output: 
         z: position of focus drive after find surface
        '''
        # FindSurface always returns None
        # exception does not work
        try:
            self.Zen.Acquisition.FindSurface()        
            z = self.Zen.Devices.Focus.ActualPosition
        except:
            raise HardwareError('Error in find_surface.')

        # Track absolute focus position for recovery in case of Definite Focus failure
        self.set_last_known_focus_position(z)
        return z

    def store_focus(self):
        '''Store actual focus position as offset from coverslip.
        
        Input:
         none
         
        Output:
         z: position of focus drive after store focus
         
        Stored focus position is lost when switching objective, even when returning to original objective.
        '''
        # check if correct objective was selected
        if self.get_objective_name() == '':
            self.set_autofocus_not_ready()
            raise AutofocusError(message='No objective selected to store autofocus position.')
        try:
            self.Zen.Acquisition.StoreFocus()
            z = self.Zen.Devices.Focus.ActualPosition
        except:
            raise HardwareError('Error in store_focus.')
        # Get objective used to set Definite Focus (Definite Focus will lose stored focus position after change of objective)
        self.DFObjective = self.get_objective_name()
        # Save stored position. We will use this position to move the objective to this position before recalling this positions
        # If the stored position is close to the find_surface position, Definite Focus works much faster.
        self.DFStoredFocus = z
        self.set_autofocus_ready()
        
        # track absolute focus position for recovery in case of Definite Focus failure
        self.set_last_known_focus_position(z)

        return z
        
    def recall_focus(self):
        '''Find stored focus position as offset from coverslip.
        
        Input:
         none
         
        Output:
         z: position of focus drive after recall focus
         
        Stored focus position is lost when switching objective, even when returning to original objective.
        '''
        # Zen.Acquisition.RecallFocus will fail if Zen cannot find a stored position.
        # This can happen if the objective was switched. After each objective switch a new focus position has to be stored within Zen.
        # We do not know a way to catch a failure directly (tired exception and time out)
        # Therefore we try to catch common indicators that RecallFocus will fail/failed
        
        # If autofocus is not ready raise exception
        self.get_autofocus_ready()
        # Is z position after RecallFocus the same
        try:
            # Move the objective to the stored focus position before recalling this positions
            # If the stored position is close to the find_surface position, Definite Focus works much faster.
            self.move_focus_to(self.DFStoredFocus)
            self.Zen.Acquisition.RecallFocus()
            # Store position, that will keep definite focus in optimal operational range
            print ('From connectZenBlue.self.Zen.Devices.Focus: {}'.format(self.Zen.Devices.Focus))
            z = self.store_focus()
        except:
            raise HardwareError('Error in recall_focus.')
        # track absolute focus position for recovery in case of Definite Focus failure
        self.set_last_known_focus_position(z)
        return z
    
    def get_focus_pos(self):
        '''Return current position of focus drive.
        
        Return:
         zPos: position of focus drive in micrometer
        '''
        ## Get current stage position
        try:
            zPos = self.Zen.Devices.Focus.ActualPosition
        except:
            raise HardwareError('Error in get_focus_pos.')
        return zPos

    
    def move_focus_to(self, zPos):
        '''Move focus to new position.
        
        Input:
         zPos, yPos: new focus position in micrometers.
        '''
 
        # an alternative to set the position
        try:
            self.Zen.Devices.Focus.TargetPosition = zPos
#             print ('2.1: ID for self.Zen.Devices.Focus.ActualPosition: {}'.format(id(self.Zen.Devices.Focus.ActualPosition)))
            self.Zen.Devices.Focus.Apply()
#             print ('2.2: ID for self.Zen.Devices.Focus.ActualPosition: {}'.format(id(self.Zen.Devices.Focus.ActualPosition)))
            # check new position
            zFocus = self.Zen.Devices.Focus.ActualPosition
#             print ('2.3 ID for self.Zen.Devices.Focus.ActualPosition: {}'.format(id(self.Zen.Devices.Focus.ActualPosition)))
        except:
            raise HardwareError('Error in move_focus_to.')
# gives type error        

        return zFocus

    def z_relative_move(self, delta):
        '''Move focus relative to current position.
        
        Input:
         delta: distance in mum
        
        Output: 
         z: new position of focus drive
        '''
        try:
            zStart = self.Zen.Devices.Focus.ActualPosition
            zEndCalc = zStart + delta
            self.Zen.Devices.Focus.MoveTo(zEndCalc)
            z = self.Zen.Devices.Focus.ActualPosition
        except:
            raise HardwareError('Error in z_relative_move.')
        return z
     
    def z_down_relative(self, delta):
        '''Move focus relative to current position away from sample.
        
        Input:
         delta: absolute distance in mum
        
        Output: 
         z: new position of focus drive
        '''
        z = self.z_relative_move(-delta)
        return z


    def z_up_relative(self, delta):
        '''Move focus relative to current position towards sample.
        
        Input:
         delta: absolute distance in mum
        
        Output: 
         z: new position of focus drive
        '''
        z = self.z_relative_move(delta)
        return z   

    def set_focus_work_position(self):
        '''retrieve current position and set as work position.
        
        Input:
         none
         
        Output:
         z_work: current focus position in mum
        '''
        zWork=self.get_focus_pos()
        self.zWork=zWork
        
        log.info('Stored current focus position as work position', str(zWork))
                
        return zWork
        
    def set_focus_load_position(self):
        '''retrieve current position and set as load position.
        
        Input:
         none
         
        Output:
         zLoad: current focus position in mum
        '''
        zLoad=self.get_focus_pos()
        self.zLoad=zLoad
        
        log.info('Stored current focus position as load position: %s', str(zLoad))
                
        return zLoad

    def move_focus_to_load(self):
        '''Move focus to load position if defined.
        
        Input:
         zPos, yPos: new focus position in micrometers.
        '''
        # check if load position is defined
        if self.zLoad == None:
            log.error('Load position not defined')
            raise LoadNotDefinedError('Tried to move focus drive to load position, but load position was not defined.')
        
        if self.zLoad > 1000:
            log.error('Load position to high')
            raise LoadNotDefinedError('Tried to move focus drive to load position, but load position was to high.')
            
        # move to load position if defined
        zFocus = self.move_focus_to(self.zLoad)
         
        log.info('moved focus to load position: %s', str(zFocus))
      
        return zFocus

    def move_focus_to_work(self):
        '''Move focus to work position if defined.
        
        Input:
         zPos, yPos: new focus position in micrometers.
        '''
        # check if load position is defined
        if self.zLoad == None:
            log.error('Work position not defined')
            return None
        
        # move to load position if defined
        zFocus = self.move_focus_to(self.zWork)
        
        log.info('moved focus to load position: %s', str(zFocus))
      
        return zFocus

##################################################################################################################
#
# Methods to interact with objectives and objective turret
#
##################################################################################################################

    def get_all_objectives(self, nPositions):
        '''Retrieve name and magnification of all objectives.
        Warning! The objectives will move.
        
        Input:
         nPositions:  number of objective positions
         
        Output:
         objectivesDict: dictionary of all objectives mounted at microscope 
                         in form {'magnification': {'Position': position, 'Name': name}
        '''
        
        try:
            # retrieve ZEN ObjectiveChanger object
            objective_changer = self.Zen.Devices.ObjectiveChanger
            objectivesDict={}
    
            for position in range(1, nPositions+1):
                magnification = objective_changer.GetMagnificationByPosition(position)
                name = objective_changer.GetNameByPosition(position)
                objectivesDict[magnification] = {'Position' : position, 'Name': name}
                objinfo = ''
                objinfo = objinfo + ' ' + format(position)
                objinfo = objinfo + '\t' + format(magnification)
                objinfo = objinfo + '\t' + name
                print objinfo
        except:
            raise HardwareError('Error in get_all_objectives.')
        return objectivesDict

    def switch_objective(self, targetPosition, load = True):
        '''Switches objective.
        
        Input:
         targetPosition: Position of new objective on objective switcher
         load: if True, move objective to load position before switching
                 Default: True
         
        Output:
         objectiveName: name of new objective
        '''
        # move focus drive to load position
        focus = self.get_focus_pos()  
        if load:
            self.move_focus_to_load()
        
        # get name of original objective. We have to let autofocus know if we really changed the objective
        originalObjectiveName = self.get_objective_name()

        try:
            # retrieve ZEN ObjectiveChanger object
            objRevolver = self.Zen.Devices.ObjectiveChanger
            
            # switch objective
            objRevolver.TargetPosition = targetPosition
            objRevolver.Apply()
            
            # get name of new objective
            objectiveName = self.get_objective_name()
        except:
            raise HardwareError('Error in switch_objective.')
            
        # move focus drive back to original position
        self.move_focus_to(focus)

        # check if objective was really changed
        if objectiveName != originalObjectiveName:
        # because objectives where changed the stored focus position for definite focus is no longer available
            self.set_autofocus_not_ready()

        return objectiveName

    def get_objective_magnification(self):
        '''Get magnification of actual objective.
        
        Input: 
         none
         
        Output: 
         magnification: magnification of actual objective, objective in imaging position
        '''
        try:
            # retrieve ZEN ObjectiveChanger object
            objRevolver = self.Zen.Devices.ObjectiveChanger
            
            # get magnification
            magnification = objRevolver.Magnification
        except:
            raise HardwareError('Error in get_objective_magnification.')
        return magnification
    
    def get_objective_name(self):
        '''Get name of actual objective.
        
        Input: 
         none
         
        Output: 
         name: name of actual objective, objective in imaging position
        '''
        try:
            # retrieve ZEN ObjectiveChanger object
            objRevolver = self.Zen.Devices.ObjectiveChanger
            
            # get name of objective
            name = objRevolver.ActualPositionName
        except:
            raise HardwareError('Error in get_objective_name.')
        return name
    
    def get_objective_position(self):
        '''Get position of actual objective.
        
        Input: 
         none
         
        Output: 
         position: position of actual objective, objective in imaging position
        '''
        try:
            # retrieve ZEN ObjectiveChanger object
            objRevolver = self.Zen.Devices.ObjectiveChanger
            
            # get name of objective
            position = objRevolver.ActualPosition
        except:
            raise HardwareError('Error in get_objective_name.')
        return position
    
##################################################################################################################
#
# Methods to control immersion water delivery
#
##################################################################################################################
      
    def trigger_pump(self, seconds, port='COM1', baudrate=19200):
        '''Trigger pump
        
        Input:
         seconds: the number of seconds pump is activated
         port: com port, default = 'COM1'
         baudrate: baudrate for connection, can be set on pump, typically = 19200
         
        Output:
         none
        '''
        try:
            # connect to pump through RS232
            pump=Braintree(port='COM1', baudrate=19200)
        
            #activate pump
            pump.start_pump()
            
            # continue pumping for seconds
            time.sleep(seconds)
            
            # stop pump and close connection
            pump.close_connection()
        except:
            raise HardwareError('Error in trigger_pump.')
        
        log.debug('Pump activated for : %s sec', seconds)

##################################################################################################################
#
# Methods to collect information about microsocpe
#
##################################################################################################################
            
    def get_microscope_name(self):
        '''Returns name of the microscope from hardware that is controlled by this class.
        
         Return:
          Microscope: name of Microscope'''
        
        name='get_microscope_name not implemented'
        log.info('This class controls the microscope: %s', name)
        return name
 
    def stop(self):
        '''Stop Microscope immediately'''
        log.info('Microscope operation aborted')

############################################################################################################################
#
# Test functions
#
############################################################################################################################

def test_definite_focus(microscope, interactive = False):
    '''Test DefiniteFocus 2 with ZEN Blue on spinning disk.
    
    Input: 
     microscope: instance of class connectMicroscope
     interactive: if true allow input from microscope
     
    Output:
     success: True when test was passed
    '''
    print 'Start test_definite_focus'
    success = True
    
    print ('Test stage movement without and with auto-focus')
    path = [[34000, 40000, 8800], [35000, 40000, 8850], [35000, 41000, 8900], [34000, 40000, 8950]]
    
    # Initialize autofocus
    z_auto_focus = microscope.find_surface()    
    print ('Auto-focus found surface at {}'.format(z_auto_focus))
    
    if interactive:
        raw_input('Focus on surface and hit Enter')
        z_after_move = microscope.get_focus_pos()
    else:
        z_after_move = microscope.z_up_relative(10)
    print ('Moved focus up 10 um to new position {}'.format(z_after_move))
    z_after_store = microscope.store_focus()
    print ('Store new focus position at {}'.format(z_after_store))

    print ('Test stage movement without and with auto-focus')
    path = [[34000, 40000, z_after_move], [35000, 40000, z_after_move], [35000, 41000, z_after_move], [34000, 40000, z_after_move]]
    
    print ('\nMove stage')
#     print ('1:ID for microscope.Zen.Devices.Focus.ActualPosition: {}'.format(id(microscope.Zen.Devices.Focus.ActualPosition)))
    for auto_focus_flag in [False, True]:
        for x, y, z in path:
            print ('\nMove stage to ({}, {}, {}) with auto_focus_flag = {}'.format(x, y, z, auto_focus_flag))
            xStage, yStage = microscope.move_stage_to(x, y) 
#             print ('2:ID for microscope.Zen.Devices.Focus.ActualPosition: {}'.format(id(microscope.Zen.Devices.Focus.ActualPosition)))            
            zFocus = microscope.move_focus_to(z)
#             print ('3:ID for microscope.Zen.Devices.Focus.ActualPosition: {}'.format(id(microscope.Zen.Devices.Focus.ActualPosition)))
            if auto_focus_flag:
                z_after_recall = microscope.recall_focus()
#                 print ('4: ID for microscope.Zen.Devices.Focus.ActualPosition: {}'.format(id(microscope.Zen.Devices.Focus.ActualPosition)))
                print ('Focus after recall: {}'.format(z_after_recall))
            
            x_new, y_new = microscope.get_stage_pos()
#             print ('5: ID for microscope.Zen.Devices.Focus.ActualPosition: {}'.format(id(microscope.Zen.Devices.Focus.ActualPosition)))
            z_new = microscope.get_focus_pos()
            print ('6: New position: {}, {}, {}'.format(x_new, y_new, z_new))
#             print ('ID for microscope.Zen.Devices.Focus.ActualPosition: {}'.format(id(microscope.Zen.Devices.Focus.ActualPosition)))
   
    return success


def test_connectZenBlue(test=['test_definite_focus', 'execute_experiment', 'snap_image', 'get_all_objectives', 'trigger_pump', 'test_focus', 'save_image', 'test_stage']):
    '''Test suite to test module with Zeiss SD hardware or test hardware.
    
    Input:
     test: list with tests to perform
     
    Output: 
     success: True when test was passed
    '''
    success =True
    print 'Start test suite'
    from imageAICS import ImageAICS
    # test class connectMicroscope
    # get instance of type connectMicroscope
    # connect via .com to Zeiss ZEN blue software
    print 'Connect to microscope'
    m=connectMicroscope()                               

    # test Definite Focus 2
    if 'test_definite_focus' in test:
        if test_definite_focus(m, interactive = False):
            print 'test_definite_focus passed test'
        else:
            print 'test_definite_focus failed test'

    # test Definite Focus 2
    if 'test_definite_focus_interactive' in test:
        if test_definite_focus(m, interactive = True):
            print 'test_definite_focus passed test'
        else:
            print 'test_definite_focus failed test'
    
    # Acquire an imageAICS using settings defined within the Zeiss ZEN software (requires ZEN 2.3
    if 'execute_experiment' in test:
        print 'Start test execute_experiment'
        experiment = 'BrightfieldStack_10x.czexp'
        print 'Experiment: ', experiment
        success = m.execute_experiment(experiment)
        print 'Experiment: None'
        success = m.execute_experiment()

    
        # display imageAICS within ZEN software
        m.show_image()
        if success:
            print 'execute_experiment passed test'
        else:
            print 'execute_experiment failed test'

    if 'snap_image' in test:
        print 'Start test snap_image'
        experiment = 'BrightfieldStack_10x.czexp'
        print 'Experiment: ', experiment
        success = m.snap_image(experiment)
        print 'Experiment: None'
        success = m.snap_image()

    
        # display imageAICS within ZEN software
        m.show_image()
        if success:
            print 'snap_image passed test'
        else:
            print 'snap_image failed test'

    if 'live_mode' in test:
        print 'Start test live_mode'
        experiment = 'BrightfieldStack_10x.czexp'
        print 'Experiment: ', experiment
        print 'Start live mode for 5 sec'
        image = m.live_mode_start(experiment)
        time.sleep(5)
        m.live_mode_stop(experiment)
        print 'Live mode stopped'
        
#     test objective changer
    if 'get_all_objectives' in test:
        print 'Start test get_all_objectives'
    #     retrieve the names and magnification of all objectives
        print 'Mounted objectives: \n', m.get_all_objectives(6)
        
        print 'get_all_objectives passed test'

#     retrieve objective information
    if 'get_objective_information' in test:
        print 'Start retrieve information about objectives'
    #     retrieve the names and magnification of objective in imaging position
        print 'Magnification: ', m.get_objective_magnification()
        print 'Name: ', m.get_objective_name()
                  
        print 'get_objective_magnification and get_objective_name passed test'
         
    if 'trigger_pump' in test:
        print 'Start test trigger_pump'
    #     operate pump for 5 sec
        m.trigger_pump(seconds=5, port='COM1', baudrate=19200)
        print 'Pump triggered'
    
    if 'test_focus' in test:
        print 'Start test test_focus'
        # retrieve focus position
        zPos=m.get_focus_pos()
        print 'Focus position: ', zPos
        
        # move focus to new position
        zPos=m.move_focus_to(zPos-10)
        print 'New focus position: ', zPos
        
        # store current focus position as work position
        zPos=m.set_focus_work_position()
        print 'Focus work position: ', zPos
        
        # store current focus position as load position
        zPos=m.set_focus_load_position()
        print 'Focus load position: ', zPos

        # move focus to work position
        zPos=m.move_focus_to_work()
        print 'New focus position: ', zPos
    
        # move focus to load position
        zPos=m.move_focus_to_load()
        print 'New focus position: ', zPos
        
        print 'test_focus passed test'
    
    if 'save_image' in test:
        print 'Start test save_image'
    #     save imageAICS from within Zeiss software to disk (in czi format)
    #     filePath="F:\\Winfried\\Testdata\\testImage.czi"
        filePath="../data/testImages/testImage.czi"
        m.save_image(filePath)
              
        # create image object
        meta={'aics_filePath': filePath}
        imageTest=ImageAICS(meta=meta)
    
        # load imageAICS from file using bioFormats
        image=m.load_image(imageTest, getMeta=True)
        image.show(filePath)
        
        print 'save_image passed test'
    
    if 'test_stage' in test:
        print 'Start test test_stage'
        x, y = m.get_stage_pos()                              # retrieve stage position in mum
        print 'Stage position x: ', x, 'y: ', y
        m.move_stage_to(x+10, y+20.5)                         # move stage to specified position in mum

        print 'test_stage passed test'
    
    return success
 
if __name__ =='__main__':

#     test=['execute_experiment', 'test_definite_focus', 'test_definite_focus_interactive', 'snap_image', 'live_mode', 'get_all_objectives', 'get_objective_information', 'trigger_pump', 'test_focus', 'save_image', 'test_stage']
    test=['get_all_objectives']
    if test_connectZenBlue(test=test):
        print 'Tests performed successful: ', test
    else:
        print 'Test stopped without  success'
    
 
    